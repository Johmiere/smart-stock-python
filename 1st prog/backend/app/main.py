from __future__ import annotations

import csv
import io
import json
import logging
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.core import (
    CHRONOS_DEVICE,
    CHRONOS_ENABLED,
    CHRONOS_MODEL,
    DISCOUNT_RATE,
    GROQ_API_KEY,
    GROQ_MODEL,
    LLM_PROVIDER,
    OLLAMA_MODEL,
    OLLAMA_URL,
    SESSION_HTTPS_ONLY,
    SESSION_SECRET,
)
from app.database import SessionLocal, get_db
from app.schemas import (
    AssistantRequest,
    CheckoutRequest,
    LoginRequest,
    ProductCreate,
    RegisterRequest,
    StockAdjustment,
)
from app.security import (
    current_user,
    csrf_token,
    hash_password,
    require_csrf,
    require_owner,
    verify_password,
)
from app.services.classification import classify_item
from app.services.forecasting import ForecastEngine, daily_series, forecast_for_horizon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ssai")
STATIC_DIR = Path(__file__).resolve().parent / "static"
EVALUATION_FILE = Path(__file__).resolve().parents[1] / "evaluation_results.csv"
forecast_engine = ForecastEngine()

app = FastAPI(
    title="Smart Stock AI",
    version="1.0.0",
    description="Python FastAPI backend for the Smart Stock AI demo.",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
    max_age=60 * 60 * 8,
)
app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")


@app.on_event("startup")
def load_ai_model() -> None:
    forecast_engine.load(CHRONOS_ENABLED, CHRONOS_MODEL, CHRONOS_DEVICE)


def commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def rows(result: Any) -> list[dict]:
    return [dict(row) for row in result.mappings().all()]


def as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def mysql_for_update(db: Session) -> str:
    return " FOR UPDATE" if db.bind and db.bind.dialect.name in {"mysql", "mariadb"} else ""


def ensure_store_access(user: dict, store_id: int) -> None:
    if user["users_role"] != "owner" and int(user["store_id"]) != store_id:
        raise HTTPException(status_code=403, detail="This record is outside your store.")
    if int(user["store_id"]) != store_id:
        raise HTTPException(status_code=403, detail="Use your assigned store for this action.")


def batch_rows_for_product(db: Session, product_id: int, store_id: int, lock: bool = False) -> list[dict]:
    suffix = mysql_for_update(db) if lock else ""
    result = db.execute(
        text(
            "SELECT batch_id, quantity_remaining, expiry_date, received_at "
            "FROM stock_batch WHERE product_id = :product_id AND store_id = :store_id "
            "AND quantity_remaining > 0" + suffix
        ),
        {"product_id": product_id, "store_id": store_id},
    )
    batches = rows(result)
    batches.sort(
        key=lambda batch: (
            batch.get("expiry_date") is None,
            as_date(batch.get("expiry_date")) or date.max,
            batch.get("received_at") or datetime.max,
            int(batch["batch_id"]),
        )
    )
    return batches


def allocate_stock(
    db: Session,
    product: dict,
    quantity: int,
    movement_type: str,
    notes: str,
    user_id: int,
    sales_id: int | None = None,
    allow_expired: bool = False,
) -> list[dict]:
    """Deduct from nearest-expiry batches; caller owns the transaction."""
    batches = batch_rows_for_product(db, int(product["product_id"]), int(product["store_id"]), lock=True)
    needed = quantity
    balance = int(product.get("product_quantity") or 0)
    allocations: list[dict] = []
    for batch in batches:
        expiry = as_date(batch.get("expiry_date"))
        if expiry and expiry < date.today() and not allow_expired:
            continue
        available = int(batch["quantity_remaining"])
        taken = min(needed, available)
        if taken <= 0:
            continue
        new_batch_qty = available - taken
        new_balance = balance - taken
        db.execute(
            text("UPDATE stock_batch SET quantity_remaining = :remaining WHERE batch_id = :batch_id"),
            {"remaining": new_batch_qty, "batch_id": batch["batch_id"]},
        )
        db.execute(
            text(
                "INSERT INTO stock_movement "
                "(product_id, store_id, users_id, movement_type, quantity, previous_quantity, "
                "new_quantity, notes, batch_id, sales_id) "
                "VALUES (:product_id, :store_id, :user_id, :movement_type, :quantity, "
                ":previous_quantity, :new_quantity, :notes, :batch_id, :sales_id)"
            ),
            {
                "product_id": product["product_id"],
                "store_id": product["store_id"],
                "user_id": user_id,
                "movement_type": movement_type,
                "quantity": taken,
                "previous_quantity": balance,
                "new_quantity": new_balance,
                "notes": notes[:255],
                "batch_id": batch["batch_id"],
                "sales_id": sales_id,
            },
        )
        allocations.append({"batch_id": int(batch["batch_id"]), "quantity": taken})
        needed -= taken
        balance = new_balance
        if needed == 0:
            break
    if needed > 0:
        raise HTTPException(
            status_code=409,
            detail="Not enough unexpired batch stock. Reconcile stock batches before continuing.",
        )
    db.execute(
        text("UPDATE product SET product_quantity = :quantity WHERE product_id = :product_id"),
        {"quantity": balance, "product_id": product["product_id"]},
    )
    return allocations


def get_ai_item(db: Session, store_id: int, product_id: int) -> dict:
    product = db.execute(
        text(
            "SELECT product_id, store_id, product_name, product_barcode, product_quantity, "
            "product_date_added, product_category, product_unit, product_price, reorder_level, "
            "supplier_lead_time_days, safety_stock_units "
            "FROM product WHERE product_id = :product_id AND store_id = :store_id"
        ),
        {"product_id": product_id, "store_id": store_id},
    ).mappings().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found in this store.")
    item = dict(product)
    today = date.today()
    history_floor = today - timedelta(days=364)
    sales_result = db.execute(
        text(
            "SELECT DATE(sale_date) AS sale_date, SUM(sale_quantity) AS sale_quantity "
            "FROM sales WHERE store_id = :store_id AND product_id = :product_id "
            "AND sale_date >= :history_floor GROUP BY DATE(sale_date) ORDER BY DATE(sale_date)"
        ),
        {"store_id": store_id, "product_id": product_id, "history_floor": history_floor},
    )
    sales = rows(sales_result)
    added = as_date(item.get("product_date_added")) or today
    start_date = max(history_floor, added)
    series = daily_series(sales, start_date, today)
    history_days = max(1, len(series))
    last_28 = sum(series[-28:])
    stock = int(item.get("product_quantity") or 0)
    batches = batch_rows_for_product(db, product_id, store_id)
    expiring_dates = [
        as_date(batch.get("expiry_date"))
        for batch in batches
        if int(batch.get("quantity_remaining") or 0) > 0 and batch.get("expiry_date") is not None
    ]
    nearest_expiry = min(expiring_dates) if expiring_dates else None
    expiry_days = max(0, (nearest_expiry - today).days) if nearest_expiry else None
    # No expiry means the app can still show the fallback forecast, but must not
    # claim a perishable-stock color without a real batch date.
    analysis_horizon = expiry_days if expiry_days is not None else 30
    expiry_forecast = forecast_for_horizon(forecast_engine, series, analysis_horizon)
    lead_time = int(item.get("supplier_lead_time_days") or 0)
    lead_forecast = forecast_for_horizon(forecast_engine, series, lead_time)
    classification = classify_item(
        stock=stock,
        expiry_demand=expiry_forecast["median"] if expiry_days is not None else None,
        sold_last_28_days=last_28,
        lead_time_demand=lead_forecast["median"],
        safety_stock=int(item.get("safety_stock_units") or 0),
    )
    return {
        "product_id": product_id,
        "product_name": item["product_name"],
        "barcode": item.get("product_barcode"),
        "current_stock": stock,
        "category": item.get("product_category") or "Other",
        "unit": item.get("product_unit") or "pieces",
        "price": float(item.get("product_price") or 0),
        "reorder_level": int(item.get("reorder_level") or 0),
        "supplier_lead_time_days": lead_time,
        "safety_stock_units": int(item.get("safety_stock_units") or 0),
        "nearest_expiry": nearest_expiry,
        "days_to_expiry": expiry_days,
        "sold_last_28_days": last_28,
        "history_days": history_days,
        "data_status": "Enough data" if history_days >= 28 else "Not enough data",
        "forecast_method": expiry_forecast["method"],
        "forecast_until_expiry": round(expiry_forecast["median"], 2) if expiry_days is not None else None,
        "forecast_low": round(expiry_forecast["low"], 2) if expiry_days is not None else None,
        "forecast_high": round(expiry_forecast["high"], 2) if expiry_days is not None else None,
        "forecast_range_available": bool(expiry_forecast.get("interval_available", False)),
        "forecast_next_30_days": round(forecast_for_horizon(forecast_engine, series, 30)["median"], 2),
        "lead_time_demand": round(lead_forecast["median"], 2),
        **classification,
    }


def check_database(db: Session) -> None:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to MySQL. Start XAMPP MySQL, import the SQL files, and check backend/.env.",
        ) from exc


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{page}.html", include_in_schema=False)
def static_page(page: str) -> FileResponse:
    allowed = {
        "dashboard", "products", "stock-history", "sales",
        "low-stock", "reports", "users",
    }
    if page not in allowed:
        raise HTTPException(status_code=404, detail="Page not found.")
    return FileResponse(STATIC_DIR / f"{page}.html")


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    check_database(db)
    return {"status": "ok", "database": "connected", "backend": "FastAPI"}


@app.get("/api/auth/csrf")
def get_csrf(request: Request) -> dict:
    return {"csrf_token": csrf_token(request)}


@app.get("/api/auth/me")
def who_am_i(request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user(request, db)
    return {
        "user_id": int(user["users_id"]),
        "store_id": int(user["store_id"]),
        "role": user["users_role"],
        "first_name": user["users_fname"] or "",
        "last_name": user["users_lname"] or "",
        "email": user["cre_username"],
    }


@app.post("/api/auth/register")
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    require_csrf(request)
    email = payload.email.strip().lower()
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")
    if len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Password is too long for the configured bcrypt hash.")
    if payload.store_option == "new" and not (payload.custom_store_name or "").strip():
        raise HTTPException(status_code=422, detail="Enter a store name.")
    if payload.store_option == "existing" and not payload.store_id:
        raise HTTPException(status_code=422, detail="Choose a store.")
    try:
        exists = db.execute(
            text("SELECT cre_id FROM credential WHERE LOWER(cre_username) = :email"),
            {"email": email},
        ).first()
        if exists:
            raise HTTPException(status_code=409, detail="That email is already registered.")
        if not db.execute(
            text("SELECT brgy_id FROM barangay WHERE brgy_id = :id"),
            {"id": payload.barangay_id},
        ).first():
            raise HTTPException(status_code=422, detail="Choose a valid barangay.")
        if payload.store_option == "new":
            store_result = db.execute(
                text("INSERT INTO store (store_name, store_location) VALUES (:name, :location)"),
                {"name": payload.custom_store_name.strip()[:50], "location": "Local demo"},
            )
            store_id = int(store_result.lastrowid)
        else:
            store_id = int(payload.store_id or 0)
            if not db.execute(
                text("SELECT store_id FROM store WHERE store_id = :id"), {"id": store_id}
            ).first():
                raise HTTPException(status_code=422, detail="Choose a valid store.")
        has_owner = db.execute(
            text("SELECT users_id FROM users WHERE store_id = :store_id AND users_role = 'owner' LIMIT 1"),
            {"store_id": store_id},
        ).first()
        # The first registered account for a store becomes its owner so a clean
        # demo database can be used without a manual role-changing SQL command.
        role = "clerk" if has_owner else "owner"
        user_result = db.execute(
            text(
                "INSERT INTO users (store_id, users_fname, users_mname, users_sname, "
                "users_lname, barangay_id, users_role) VALUES "
                "(:store_id, :first_name, :middle_name, :suffix_name, :last_name, :barangay_id, :role)"
            ),
            {
                "store_id": store_id,
                "first_name": payload.first_name.strip(),
                "middle_name": payload.middle_name.strip() or None,
                "suffix_name": payload.suffix_name.strip() or None,
                "last_name": payload.last_name.strip(),
                "barangay_id": payload.barangay_id,
                "role": role,
            },
        )
        user_id = int(user_result.lastrowid)
        db.execute(
            text(
                "INSERT INTO credential (users_id, cre_username, cre_password, cre_status) "
                "VALUES (:user_id, :email, :password, 1)"
            ),
            {"user_id": user_id, "email": email, "password": hash_password(payload.password)},
        )
        commit_or_rollback(db)
        return {"message": "Account created. You can sign in now.", "role": role}
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That account or store could not be created. Check for duplicates.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Registration failed")
        raise HTTPException(status_code=503, detail="Registration failed. Check MySQL and the SSAI database extension.") from exc


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    require_csrf(request)
    email = payload.email.strip().lower()
    row = db.execute(
        text(
            "SELECT u.users_id, u.store_id, u.users_role, c.cre_password "
            "FROM credential c JOIN users u ON u.users_id = c.users_id "
            "WHERE LOWER(c.cre_username) = :email AND COALESCE(c.cre_status, 1) = 1 LIMIT 1"
        ),
        {"email": email},
    ).mappings().first()
    if not row or not verify_password(payload.password, row["cre_password"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    request.session.clear()
    request.session["user_id"] = int(row["users_id"])
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return {"message": "Signed in.", "next": "/dashboard.html", "role": row["users_role"]}


@app.post("/api/auth/logout")
def logout(request: Request) -> dict:
    require_csrf(request)
    request.session.clear()
    return {"message": "Signed out."}


@app.get("/api/locations/provinces")
def get_provinces(db: Session = Depends(get_db)) -> list[dict]:
    return rows(db.execute(text("SELECT prov_id, prov_name FROM province ORDER BY prov_name")))


@app.get("/api/locations/municipalities")
def get_municipalities(province_id: int, db: Session = Depends(get_db)) -> list[dict]:
    return rows(
        db.execute(
            text("SELECT mun_id, mun_name FROM municipality WHERE prov_id = :id ORDER BY mun_name"),
            {"id": province_id},
        )
    )


@app.get("/api/locations/barangays")
def get_barangays(municipality_id: int, db: Session = Depends(get_db)) -> list[dict]:
    return rows(
        db.execute(
            text("SELECT brgy_id, brgy_name FROM barangay WHERE mun_id = :id ORDER BY brgy_name"),
            {"id": municipality_id},
        )
    )


@app.get("/api/locations/stores")
def get_stores(db: Session = Depends(get_db)) -> list[dict]:
    return rows(db.execute(text("SELECT store_id, store_name FROM store ORDER BY store_id")))


@app.get("/api/products")
def get_products(
    request: Request,
    db: Session = Depends(get_db),
) -> list[dict]:
    user = current_user(request, db)
    result = db.execute(
        text(
            "SELECT p.product_id, p.store_id, p.product_name, p.product_barcode, "
            "COALESCE(p.product_quantity, 0) AS product_quantity, p.product_date_added, "
            "p.product_category, p.product_unit, p.product_price, p.reorder_level, "
            "p.supplier_lead_time_days, p.safety_stock_units, s.store_name, "
            "EXISTS (SELECT 1 FROM sales x WHERE x.product_id = p.product_id) AS has_sales, "
            "EXISTS (SELECT 1 FROM stock_movement m WHERE m.product_id = p.product_id) AS has_movements "
            "FROM product p LEFT JOIN store s ON s.store_id = p.store_id "
            "WHERE p.store_id = :store_id ORDER BY p.product_name, p.product_id"
        ),
        {"store_id": int(user["store_id"])},
    )
    return rows(result)


@app.get("/api/products/lookup")
def lookup_product(barcode: str, request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user(request, db)
    row = db.execute(
        text(
            "SELECT product_id, product_name, product_barcode, COALESCE(product_quantity,0) AS product_quantity, "
            "product_price, product_unit FROM product "
            "WHERE store_id = :store_id AND product_barcode = :barcode LIMIT 1"
        ),
        {"store_id": int(user["store_id"]), "barcode": barcode.strip()},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Unknown barcode. Ask the store owner to register this product.")
    return dict(row)


@app.post("/api/products")
def create_product(payload: ProductCreate, request: Request, db: Session = Depends(get_db)) -> dict:
    require_csrf(request)
    user = current_user(request, db)
    require_owner(user)
    store_id = int(user["store_id"])
    try:
        result = db.execute(
            text(
                "INSERT INTO product (store_id, product_name, product_barcode, product_quantity, "
                "product_date_added, product_category, product_unit, product_price, reorder_level, "
                "supplier_lead_time_days, safety_stock_units) "
                "VALUES (:store_id, :name, :barcode, :quantity, :today, :category, :unit, :price, "
                ":reorder, :lead, :safety)"
            ),
            {
                "store_id": store_id,
                "name": payload.product_name.strip(),
                "barcode": payload.product_barcode.strip(),
                "quantity": payload.product_quantity,
                "today": date.today(),
                "category": payload.category.strip(),
                "unit": payload.unit.strip(),
                "price": Decimal(str(payload.price)).quantize(Decimal("0.01")),
                "reorder": payload.reorder_level,
                "lead": payload.supplier_lead_time_days,
                "safety": payload.safety_stock_units,
            },
        )
        product_id = int(result.lastrowid)
        if payload.product_quantity > 0:
            batch_result = db.execute(
                text(
                    "INSERT INTO stock_batch (product_id, store_id, quantity_received, quantity_remaining, "
                    "received_at, expiry_date, notes, created_by) "
                    "VALUES (:product_id, :store_id, :quantity, :quantity, :received, :expiry, :notes, :user_id)"
                ),
                {
                    "product_id": product_id,
                    "store_id": store_id,
                    "quantity": payload.product_quantity,
                    "received": datetime.now(),
                    "expiry": payload.expiry_date,
                    "notes": "Initial stock at product registration",
                    "user_id": int(user["users_id"]),
                },
            )
            batch_id = int(batch_result.lastrowid)
            db.execute(
                text(
                    "INSERT INTO stock_movement (product_id, store_id, users_id, movement_type, quantity, "
                    "previous_quantity, new_quantity, notes, batch_id) "
                    "VALUES (:product_id, :store_id, :user_id, 'add', :quantity, 0, :quantity, :notes, :batch_id)"
                ),
                {
                    "product_id": product_id,
                    "store_id": store_id,
                    "user_id": int(user["users_id"]),
                    "quantity": payload.product_quantity,
                    "notes": "Initial stock when product was created",
                    "batch_id": batch_id,
                },
            )
        commit_or_rollback(db)
        return {"product_id": product_id, "message": "Product added successfully."}
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That barcode is already used in your store.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Product creation failed")
        raise HTTPException(status_code=503, detail="Could not add product. Apply migrations/001_ssai_demo_extension.sql.") from exc


@app.post("/api/products/{product_id}/stock-adjustments")
def adjust_stock(
    product_id: int,
    payload: StockAdjustment,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    require_csrf(request)
    user = current_user(request, db)
    store_id = int(user["store_id"])
    try:
        product_row = db.execute(
            text(
                "SELECT product_id, store_id, product_quantity FROM product "
                "WHERE product_id = :product_id AND store_id = :store_id"
                + mysql_for_update(db)
            ),
            {"product_id": product_id, "store_id": store_id},
        ).mappings().first()
        if not product_row:
            raise HTTPException(status_code=404, detail="Product not found.")
        product = dict(product_row)
        before = int(product.get("product_quantity") or 0)
        if payload.action == "increase":
            after = before + payload.quantity
            if after > 2147483647:
                raise HTTPException(status_code=422, detail="That quantity is too large.")
            batch_result = db.execute(
                text(
                    "INSERT INTO stock_batch (product_id, store_id, quantity_received, quantity_remaining, "
                    "received_at, expiry_date, notes, created_by) "
                    "VALUES (:product_id, :store_id, :quantity, :quantity, :received, :expiry, :notes, :user_id)"
                ),
                {
                    "product_id": product_id,
                    "store_id": store_id,
                    "quantity": payload.quantity,
                    "received": datetime.now(),
                    "expiry": payload.expiry_date,
                    "notes": payload.notes.strip() or "Manual stock increase; expiry unknown",
                    "user_id": int(user["users_id"]),
                },
            )
            batch_id = int(batch_result.lastrowid)
            db.execute(
                text("UPDATE product SET product_quantity = :quantity WHERE product_id = :id"),
                {"quantity": after, "id": product_id},
            )
            db.execute(
                text(
                    "INSERT INTO stock_movement (product_id, store_id, users_id, movement_type, quantity, "
                    "previous_quantity, new_quantity, notes, batch_id) "
                    "VALUES (:product_id, :store_id, :user_id, 'add', :quantity, :before, :after, :notes, :batch_id)"
                ),
                {
                    "product_id": product_id, "store_id": store_id, "user_id": int(user["users_id"]),
                    "quantity": payload.quantity, "before": before, "after": after,
                    "notes": payload.notes.strip() or "Manual stock increase",
                    "batch_id": batch_id,
                },
            )
        else:
            if before < payload.quantity:
                raise HTTPException(status_code=409, detail="Cannot reduce stock below zero.")
            allocate_stock(
                db,
                product,
                payload.quantity,
                "reduce",
                payload.notes.strip() or "Manual stock decrease",
                int(user["users_id"]),
                allow_expired=True,
            )
            after = before - payload.quantity
        commit_or_rollback(db)
        return {"product_id": product_id, "previous_quantity": before, "new_quantity": after}
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Stock adjustment failed")
        raise HTTPException(status_code=503, detail="Could not adjust stock. Check the SSAI database extension.") from exc


@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    require_csrf(request)
    user = current_user(request, db)
    require_owner(user)
    store_id = int(user["store_id"])
    activity = db.execute(
        text(
            "SELECT "
            "(SELECT COUNT(*) FROM sales WHERE product_id = :id) AS sales_count, "
            "(SELECT COUNT(*) FROM stock_movement WHERE product_id = :id) AS movement_count"
        ),
        {"id": product_id},
    ).mappings().first()
    if int(activity["sales_count"]) or int(activity["movement_count"]):
        raise HTTPException(status_code=409, detail="Products with sales or stock history stay on record.")
    db.execute(
        text("DELETE FROM stock_batch WHERE product_id = :id AND store_id = :store_id"),
        {"id": product_id, "store_id": store_id},
    )
    result = db.execute(
        text("DELETE FROM product WHERE product_id = :id AND store_id = :store_id"),
        {"id": product_id, "store_id": store_id},
    )
    if not result.rowcount:
        db.rollback()
        raise HTTPException(status_code=404, detail="Product not found.")
    commit_or_rollback(db)
    return {"message": "Product deleted."}


@app.get("/api/stock/movements")
def get_stock_movements(
    request: Request,
    product_id: int | None = None,
    movement_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
) -> dict:
    user = current_user(request, db)
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    clauses = ["m.store_id = :store_id"]
    params: dict[str, Any] = {"store_id": int(user["store_id"])}
    if product_id:
        clauses.append("m.product_id = :product_id")
        params["product_id"] = product_id
    if movement_type in {"add", "reduce", "return"}:
        clauses.append("m.movement_type = :movement_type")
        params["movement_type"] = movement_type
    if date_from:
        clauses.append("m.movement_date >= :date_from")
        params["date_from"] = datetime.combine(date_from, datetime.min.time())
    if date_to:
        clauses.append("m.movement_date < :date_to")
        params["date_to"] = datetime.combine(date_to + timedelta(days=1), datetime.min.time())
    where = " AND ".join(clauses)
    total = db.execute(
        text("SELECT COUNT(*) FROM stock_movement m WHERE " + where), params
    ).scalar_one()
    params.update({"limit": page_size, "offset": (page - 1) * page_size})
    movements = rows(
        db.execute(
            text(
                "SELECT m.movement_id, m.product_id, m.store_id, m.users_id, m.movement_type, "
                "m.quantity, m.previous_quantity, m.new_quantity, m.notes, m.movement_date, m.batch_id, "
                "p.product_name, u.users_fname, u.users_lname "
                "FROM stock_movement m LEFT JOIN product p ON p.product_id = m.product_id "
                "LEFT JOIN users u ON u.users_id = m.users_id WHERE " + where
                + " ORDER BY m.movement_date DESC, m.movement_id DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        )
    )
    return {"items": movements, "total": int(total), "page": page, "page_size": page_size}


@app.get("/api/stock")
def get_stock(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    user = current_user(request, db)
    return rows(
        db.execute(
            text(
                "SELECT p.product_id, p.product_name, p.product_barcode, "
                "COALESCE(p.product_quantity,0) AS current_stock, "
                "(SELECT MIN(b.expiry_date) FROM stock_batch b WHERE b.product_id=p.product_id "
                "AND b.quantity_remaining>0 AND b.expiry_date IS NOT NULL) AS nearest_expiry "
                "FROM product p WHERE p.store_id=:store_id ORDER BY p.product_name"
            ),
            {"store_id": int(user["store_id"])},
        )
    )


@app.post("/api/sales")
def checkout(payload: CheckoutRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    require_csrf(request)
    user = current_user(request, db)
    store_id = int(user["store_id"])
    user_id = int(user["users_id"])
    cart: list[dict] = []
    subtotal = Decimal("0.00")
    for line in payload.items:
        if line.product_id:
            row = db.execute(
                text(
                    "SELECT product_id, store_id, product_name, product_barcode, product_quantity, product_price "
                    "FROM product WHERE product_id = :id AND store_id = :store_id"
                ),
                {"id": line.product_id, "store_id": store_id},
            ).mappings().first()
        else:
            row = db.execute(
                text(
                    "SELECT product_id, store_id, product_name, product_barcode, product_quantity, product_price "
                    "FROM product WHERE product_barcode = :barcode AND store_id = :store_id"
                ),
                {"barcode": (line.barcode or "").strip(), "store_id": store_id},
            ).mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail=f"Unknown product/barcode: {line.barcode or line.product_id}")
        product = dict(row)
        if int(product.get("product_quantity") or 0) < line.quantity:
            raise HTTPException(status_code=409, detail=f"Insufficient stock for {product['product_name']}.")
        unit_price = Decimal(str(product.get("product_price") or 0)).quantize(Decimal("0.01"))
        line_total = unit_price * line.quantity
        subtotal += line_total
        cart.append({"product": product, "quantity": line.quantity, "unit_price": unit_price, "line_total": line_total})
    rate = Decimal(str(DISCOUNT_RATE)) if payload.discount_type in {"pwd", "senior"} else Decimal("0")
    discount = (subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = max(Decimal("0.00"), subtotal - discount)
    try:
        transaction_result = db.execute(
            text(
                "INSERT INTO sale_transaction (store_id, users_id, subtotal, discount_type, "
                "discount_reference, discount_amount, total_amount) "
                "VALUES (:store_id, :user_id, :subtotal, :discount_type, :reference, :discount, :total)"
            ),
            {
                "store_id": store_id,
                "user_id": user_id,
                "subtotal": subtotal,
                "discount_type": payload.discount_type,
                "reference": payload.discount_reference.strip() or None,
                "discount": discount,
                "total": total,
            },
        )
        transaction_id = int(transaction_result.lastrowid)
        sale_ids = []
        allocated_discount = Decimal("0.00")
        for index, entry in enumerate(cart):
            product = entry["product"]
            if index == len(cart) - 1:
                line_discount = discount - allocated_discount
            elif subtotal:
                line_discount = (
                    (entry["line_total"] / subtotal * discount).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                )
                allocated_discount += line_discount
            else:
                line_discount = Decimal("0.00")
            sale_result = db.execute(
                text(
                    "INSERT INTO sales (store_id, product_id, sale_quantity, sale_transaction_id, "
                    "sale_unit_price, sale_discount_amount) "
                    "VALUES (:store_id, :product_id, :quantity, :transaction_id, :price, :discount)"
                ),
                {
                    "store_id": store_id,
                    "product_id": product["product_id"],
                    "quantity": entry["quantity"],
                    "transaction_id": transaction_id,
                    "price": entry["unit_price"],
                    "discount": line_discount,
                },
            )
            sale_id = int(sale_result.lastrowid)
            sale_ids.append(sale_id)
            locked_product = db.execute(
                text(
                    "SELECT product_id, store_id, product_quantity FROM product "
                    "WHERE product_id = :id AND store_id = :store_id" + mysql_for_update(db)
                ),
                {"id": product["product_id"], "store_id": store_id},
            ).mappings().first()
            if int(locked_product["product_quantity"] or 0) < entry["quantity"]:
                raise HTTPException(status_code=409, detail=f"Stock changed during checkout for {product['product_name']}.")
            allocate_stock(
                db,
                dict(locked_product),
                entry["quantity"],
                "reduce",
                f"Completed sale #{transaction_id}",
                user_id,
                sales_id=sale_id,
            )
        commit_or_rollback(db)
        return {
            "transaction_id": transaction_id,
            "sales_ids": sale_ids,
            "subtotal": float(subtotal),
            "discount": float(discount),
            "total": float(total),
            "message": "Sale completed and stock was deducted from the nearest-expiry batches.",
        }
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Checkout failed")
        raise HTTPException(status_code=503, detail="Checkout failed. Check the SSAI database extension.") from exc


@app.get("/api/sales")
def get_sales(request: Request, limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    user = current_user(request, db)
    limit = min(200, max(1, limit))
    return rows(
        db.execute(
            text(
                "SELECT s.sales_id, s.sale_date, s.sale_quantity, s.sale_unit_price, "
                "s.sale_discount_amount, s.sale_transaction_id, p.product_name, p.product_barcode, "
                "t.discount_type, t.total_amount "
                "FROM sales s JOIN product p ON p.product_id=s.product_id "
                "LEFT JOIN sale_transaction t ON t.transaction_id=s.sale_transaction_id "
                "WHERE s.store_id=:store_id ORDER BY s.sale_date DESC, s.sales_id DESC LIMIT :limit"
            ),
            {"store_id": int(user["store_id"]), "limit": limit},
        )
    )


@app.get("/api/sales/best-sellers")
def get_best_sellers(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    user = current_user(request, db)
    start = date.today() - timedelta(days=29)
    return rows(
        db.execute(
            text(
                "SELECT p.product_id, p.product_name, p.product_barcode, "
                "SUM(s.sale_quantity) AS sold_last_30_days "
                "FROM sales s JOIN product p ON p.product_id=s.product_id "
                "WHERE s.store_id=:store_id AND s.sale_date>=:start "
                "GROUP BY p.product_id, p.product_name, p.product_barcode "
                "ORDER BY sold_last_30_days DESC, p.product_name LIMIT 5"
            ),
            {"store_id": int(user["store_id"]), "start": start},
        )
    )


@app.get("/api/public-config")
def public_config() -> dict:
    return {"special_discount_rate": DISCOUNT_RATE}


@app.get("/api/dashboard/summary")
def dashboard_summary(request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user(request, db)
    store_id = int(user["store_id"])
    today = date.today()
    first_day = today - timedelta(days=6)
    sales_rows = rows(
        db.execute(
            text(
                "SELECT DATE(sale_date) AS sale_day, SUM(sale_quantity) AS quantity, "
                "COUNT(*) AS line_count FROM sales WHERE store_id=:store_id AND sale_date>=:start "
                "GROUP BY DATE(sale_date) ORDER BY DATE(sale_date)"
            ),
            {"store_id": store_id, "start": first_day},
        )
    )
    by_day = {as_date(row["sale_day"]): row for row in sales_rows}
    chart = []
    for offset in range(7):
        day = first_day + timedelta(days=offset)
        row = by_day.get(day, {})
        chart.append(
            {
                "date": day.isoformat(),
                "label": day.strftime("%b %d"),
                "quantity": int(row.get("quantity") or 0),
                "orders": int(row.get("line_count") or 0),
            }
        )
    products_count = int(
        db.execute(text("SELECT COUNT(*) FROM product WHERE store_id=:id"), {"id": store_id}).scalar_one()
    )
    stock_total = int(
        db.execute(
            text("SELECT COALESCE(SUM(product_quantity),0) FROM product WHERE store_id=:id"),
            {"id": store_id},
        ).scalar_one()
    )
    return {
        "store_name": db.execute(text("SELECT store_name FROM store WHERE store_id=:id"), {"id": store_id}).scalar_one_or_none(),
        "weekly_sales_quantity": sum(day["quantity"] for day in chart),
        "weekly_sale_lines": sum(day["orders"] for day in chart),
        "products_count": products_count,
        "stock_units": stock_total,
        "chart": chart,
    }


@app.get("/api/ai/items")
def ai_items(
    request: Request,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    user = current_user(request, db)
    product_ids = [
        int(row[0])
        for row in db.execute(
            text("SELECT product_id FROM product WHERE store_id=:id ORDER BY product_name"),
            {"id": int(user["store_id"])},
        ).all()
    ]
    items = [get_ai_item(db, int(user["store_id"]), product_id) for product_id in product_ids]
    if status == "blue":
        items = [item for item in items if item["low_stock"]]
    elif status in {"red", "yellow", "green", "unknown"}:
        items = [item for item in items if item["status"] == status]
    return {
        "items": items,
        "model": CHRONOS_MODEL if forecast_engine.pipeline is not None else "moving_average_fallback",
        "chronos_loaded": forecast_engine.pipeline is not None,
        "chronos_error": forecast_engine.model_error,
    }


@app.get("/api/ai/items/{product_id}")
def ai_item(product_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user(request, db)
    return get_ai_item(db, int(user["store_id"]), product_id)


@app.get("/api/ai/evaluation")
def ai_evaluation(request: Request, db: Session = Depends(get_db)) -> dict:
    user = current_user(request, db)
    if EVALUATION_FILE.exists():
        with EVALUATION_FILE.open("r", newline="", encoding="utf-8") as handle:
            stored = list(csv.DictReader(handle))
        return {"status": "available", "results": stored, "source": "evaluation_results.csv"}
    sales_count = db.execute(
        text("SELECT COUNT(*) FROM sales WHERE store_id=:id"),
        {"id": int(user["store_id"])},
    ).scalar_one()
    return {
        "status": "not_evaluated",
        "results": [],
        "message": (
            "No evaluation_results.csv exists yet. Use at least 28 days of real item sales and run the "
            "evaluation notebook before reporting model metrics."
        ),
        "sales_rows_available": int(sales_count),
    }


@app.post("/api/imports/sales")
async def import_sales(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    require_csrf(request)
    user = current_user(request, db)
    require_owner(user)
    raw = await file.read()
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Use a UTF-8 CSV file.") from exc
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="The CSV needs headers: date, barcode, qty_sold.")
    names = {name.strip().lower() for name in reader.fieldnames if name}
    if not {"date", "barcode", "qty_sold"}.issubset(names):
        raise HTTPException(status_code=400, detail="The CSV needs date, barcode, qty_sold columns.")
    imported = 0
    errors = []
    for line_number, raw_row in enumerate(reader, start=2):
        row = {str(k).strip().lower(): (v or "").strip() for k, v in raw_row.items() if k}
        try:
            sale_time = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
            if sale_time.tzinfo is not None:
                sale_time = sale_time.astimezone().replace(tzinfo=None)
            barcode = row["barcode"]
            quantity = int(row["qty_sold"])
            if quantity <= 0:
                raise ValueError("qty_sold must be positive")
            product = db.execute(
                text(
                    "SELECT product_id FROM product WHERE store_id=:store_id AND product_barcode=:barcode"
                ),
                {"store_id": int(user["store_id"]), "barcode": barcode},
            ).first()
            if not product:
                raise ValueError(f"unknown barcode {barcode}")
            tx_result = db.execute(
                text(
                    "INSERT INTO sale_transaction (store_id, users_id, subtotal, discount_type, "
                    "discount_amount, total_amount, created_at) VALUES "
                    "(:store, :user, 0, 'none', 0, 0, :created_at)"
                ),
                {
                    "store": int(user["store_id"]),
                    "user": int(user["users_id"]),
                    "created_at": sale_time,
                },
            )
            db.execute(
                text(
                    "INSERT INTO sales (store_id, product_id, sale_quantity, sale_date, "
                    "sale_transaction_id, sale_unit_price, sale_discount_amount) VALUES "
                    "(:store, :product, :quantity, :sale_time, :tx, 0, 0)"
                ),
                {
                    "store": int(user["store_id"]),
                    "product": int(product[0]),
                    "quantity": quantity,
                    "sale_time": sale_time,
                    "tx": int(tx_result.lastrowid),
                },
            )
            imported += 1
        except Exception as exc:
            errors.append({"line": line_number, "error": str(exc)})
    if imported:
        commit_or_rollback(db)
    else:
        db.rollback()
    return {
        "imported_rows": imported,
        "skipped_rows": len(errors),
        "errors": errors[:100],
        "note": "Historical rows are imported for forecasting; they do not change current stock.",
    }


async def call_assistant_provider(question: str, retrieved: dict) -> str | None:
    system = (
        "You are Smart Stock AI, a grocery inventory assistant. Answer only from the retrieved JSON facts. "
        "Do not invent quantities, expiry dates, prices, forecasts, or actions. If the facts are missing, say so. "
        "Keep the answer concise and mention which product facts support it."
    )
    prompt = json.dumps(retrieved, default=str, ensure_ascii=False)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Question: " + question + "\nRetrieved facts JSON: " + prompt},
    ]
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            if LLM_PROVIDER == "groq" and GROQ_API_KEY:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": "Bearer " + GROQ_API_KEY},
                    json={"model": GROQ_MODEL, "messages": messages, "temperature": 0.2},
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            if LLM_PROVIDER == "ollama":
                response = await client.post(
                    OLLAMA_URL,
                    json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
                )
                response.raise_for_status()
                return response.json().get("message", {}).get("content")
    except Exception:
        logger.exception("Configured assistant provider failed; using local grounded response.")
    return None


@app.post("/api/assistant/ask")
async def assistant_ask(
    payload: AssistantRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    require_csrf(request)
    user = current_user(request, db)
    store_id = int(user["store_id"])
    if payload.product_id:
        selected = get_ai_item(db, store_id, payload.product_id)
        retrieved_items = [selected]
    else:
        product_rows = rows(
            db.execute(
                text(
                    "SELECT product_id, product_name, product_barcode FROM product "
                    "WHERE store_id=:store_id ORDER BY product_name"
                ),
                {"store_id": store_id},
            )
        )
        question = payload.question.lower()
        matched = [
            item for item in product_rows
            if item["product_name"].lower() in question
            or (item.get("product_barcode") and item["product_barcode"].lower() in question)
        ]
        chosen = matched[:3] if matched else product_rows[:3]
        retrieved_items = [
            get_ai_item(db, store_id, int(item["product_id"])) for item in chosen
        ]
    facts = {"items": retrieved_items}
    answer = await call_assistant_provider(payload.question, facts)
    if not answer:
        if not retrieved_items:
            answer = "Wala pang product data sa store. Magdagdag muna ng produkto at stock."
        else:
            item = retrieved_items[0]
            expiry = item["nearest_expiry"] or "walang nakatalang expiry"
            answer = (
                f"{item['product_name']} has {item['current_stock']} {item['unit']} in stock; "
                f"nearest expiry: {expiry}; forecast: {item['forecast_until_expiry']} "
                f"units before expiry; status: {item['status']}. {item['suggested_action']}"
            )
    return {"answer": answer, "data_used": facts, "provider": LLM_PROVIDER if LLM_PROVIDER != "none" else "local"}


@app.get("/api/users")
def get_users(request: Request, db: Session = Depends(get_db)) -> list[dict]:
    user = current_user(request, db)
    require_owner(user)
    return rows(
        db.execute(
            text(
                "SELECT u.users_id, u.users_fname, u.users_lname, u.users_role, "
                "c.cre_username FROM users u JOIN credential c ON c.users_id=u.users_id "
                "WHERE u.store_id=:store_id ORDER BY u.users_id"
            ),
            {"store_id": int(user["store_id"])},
        )
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database operation failed", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database operation failed. Check MySQL and the SSAI demo extension SQL."},
    )

