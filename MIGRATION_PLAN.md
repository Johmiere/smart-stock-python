# Smart Stock AI (SSAI) Migration Plan

## Scope and evidence

This audit follows the attached final plan, upload/SSAI-System-Plan.md, as the source of truth for the target features, algorithms, stack, and build sequence. I inspected the complete SQL source, every PHP file, the current FastAPI service, the supplied HTML/CSS/JavaScript, README.md, GROUPMATE_SETUP.md, and GITHUB_UPLOAD.md in the supplied smart-stock-demo-main.zip. No application code was changed for this audit.

The SQL file is a clean groupmate demo setup for inventory_group_demo, not the owner's current production export. Its comments and setup guide say it contains geography data and one Demo Store, but no users, credentials, products, or sales. The guides identify inventory_restore_20260930 as a separate live database that is not included. Findings below therefore describe the supplied demo schema and source only. The schema and data in the live database are NOT FOUND in this package.

I did not start the application or run tests. In the status column, “working” means the flow is represented in the source; it is not a runtime guarantee. Runtime setup still requires importing the SQL, creating the ignored local db_connection.php from the example, and starting the appropriate services.

## 1. Current features, implementation files, and status

| Feature | Files that implement it | Status and audit notes |
|---|---|---|
| Sign in, sign out, and account registration | 1st prog/index.html; 1st prog/js/script.js; 1st prog/php/auth/login.php; 1st prog/php/auth/logout.php; 1st prog/php/auth/register.php; SQL procedures in database/groupmate_clean_setup.sql | Partial. The forms, bcrypt password verification/hash, PHP sessions, location selection, optional new-store creation, and account creation are implemented. The clean SQL has no account, so a user must register. Registration assigns the database default role, clerk. There is no in-app first-owner/bootstrap flow; GROUPMATE_SETUP.md requires a manual SQL role update before that account can add products. |
| Province, municipality, barangay, and store selectors | 1st prog/index.html; 1st prog/js/script.js; 1st prog/php/locations/get_provinces.php; get_municipalities.php; get_barangays.php; get_stores.php; stored procedures in database/groupmate_clean_setup.sql | Working in the existing PHP setup, subject to database configuration. The JavaScript fetches JSON and cascades the location selectors. The store table is not linked to a geographic ID; the location selected at registration belongs to the user. |
| Dashboard cards, charts, and prediction list | 1st prog/php/dashboard.php; 1st prog/html/dashboard.html; 1st prog/css/style.css | Partial. It computes seven-day sales totals, order-row counts, product count, a hard-coded quantity-at-or-below-10 low-stock count, and summaries from ai_prediction. The current baseline service does not write ai_prediction rows, so its results do not populate the dashboard prediction list. The dashboard SQL does not scope sales, products, or predictions to the signed-in user's store. |
| Product list, product creation, and deletion guard | 1st prog/php/products/product_management.php; add_product.php; adjust_stock.php; 1st prog/html/product_management.html; 1st prog/css/style.css | Partial. Owners can add a name, barcode/SKU, and starting quantity; the list shows store, quantity, and date added. An owner can delete only a product with no sales or stock movements. Users created by registration are clerks and cannot add products until manually promoted. Category, unit, price, reorder level, supplier lead time, and expiry are absent. |
| Manual stock increase/decrease | 1st prog/php/products/adjust_stock.php; 1st prog/php/inventory/reduce_stock.php; 1st prog/html/product_management.html | Working for aggregate product quantity in the supplied code path. Updates are transactional, reject negative stock, and write a movement row with actor, quantity, before/after, notes, and timestamp. An increase does not capture an individual delivery batch or expiry date. |
| Stock history and filters | 1st prog/php/inventory/inventory_tracking.php; 1st prog/html/inventory_tracking.html; 1st prog/php/products/add_product.php; adjust_stock.php; 1st prog/php/sales/record_sale.php | Working for movements recorded after this feature was added. Supports product/type/date filters, pagination, current-stock totals, and owner all-store view. It cannot reconstruct movements that were not previously logged and has no batch or expiry history. |
| Barcode POS sale | 1st prog/php/sales/sales_transactions.php; 1st prog/php/sales/record_sale.php; 1st prog/html/sales_transactions.html | Partial. A USB keyboard-style scanner or manual barcode entry can submit one product and quantity after checkout confirmation. The sale, aggregate stock deduction, and stock movement are transactional; a row stores product, quantity, store, and timestamp. There is no cart, line price, discount, PWD/Senior Citizen handling, camera scanner, payment record, or batch-FIFO allocation. Unknown barcodes produce an error; they do not open product registration. |
| Best sellers and recent completed sales | 1st prog/php/sales/sales_transactions.php; 1st prog/html/sales_transactions.html | Working for the current store and available rows. Counts are based on quantities over the last 30 days; recent sales show the latest 25 item rows. The clean export has no sale rows. |
| Current Python monitoring/baseline | 1st prog/fastapi-service/main.py; 1st prog/fastapi-service/requirements.txt; called by 1st prog/php/sales/sales_transactions.php | Partial. POST /analyze accepts product signals and returns a copied 30-day sales baseline, projected stock, shortage, and heuristic label. It has no database connection, model loading, expiry input, Chronos, classification rules from the final plan, cache, scheduled run, RAG, or evaluation. requirements.txt contains only FastAPI and Uvicorn; SQLAlchemy, a MySQL driver, Chronos dependencies, and LLM client are absent. |
| Low-stock page | 1st prog/php/inventory/low_stock.php; 1st prog/html/low_stock.html; dashboard query in 1st prog/php/dashboard.php | Broken/placeholder relative to its label. The page says it is ready for future automation and does not query or list low-stock products. The dashboard uses a fixed threshold of 10, not a product reorder level or lead-time forecast. |
| Reports and analytics | 1st prog/php/reports/reports.php; 1st prog/html/reports.html | Broken/placeholder. The page says it is ready for future workflows; no report data or export is produced. |
| User management | 1st prog/php/users/user_management.php; 1st prog/html/user_management.html | Broken/placeholder. The page says future user-admin tools; no user listing, role editing, or access-management endpoint exists. The schema only has owner and clerk roles, not the plan's IT Admin role. |
| Login/register UI behavior and styling | 1st prog/index.html; 1st prog/js/script.js; 1st prog/css/style.css; 1st prog/html/*.html | Partial for the target static frontend. Current PHP includes render PHP expressions embedded in files named .html. Those files are templates, not ready-to-serve static pages. They must be converted to ordinary HTML/JS that fetches API data. |
| MySQL/PHP configuration | 1st prog/php/config/db_connection.example.php; 1st prog/php/config/sales_monitoring_migration.sql; database/groupmate_clean_setup.sql; README.md; GROUPMATE_SETUP.md | Partial setup. The real php/config/db_connection.php is intentionally not in the ZIP and must be copied locally from the example. The archive also has no .git directory, so it does not include repository history or a migration branch. |
| CSV/Excel import and historical-sales upload | No implementation found | Not available. The final plan requires importing historical sales and products, but there is no importer, upload UI, parser, or import endpoint in the archive. |
| Expiry-aware inventory, stock-in batches, and FEFO/FIFO deduction | No implementation found; aggregate stock is product.product_quantity | Not available. Current sales decrement the one product-level quantity. There is no batch table, per-batch expiry, or allocation history. |
| Chronos forecast, moving-average fallback, RAG assistant, and evaluation | No implementation found; see current baseline above | Not available. These are target-plan capabilities, not current features. |

### Current baseline rule order

The supplied FastAPI code classifies signals in this order: possible deadstock if stock is positive, product age is at least 90 days, and sold_90d is zero; slow-moving if stock is positive, age is at least 30 days, and sold_30d is at most 2; stockout risk if the 30-day baseline exceeds stock; collecting history if age is under 30 days; otherwise active. Because this is an if/elif chain, an earlier condition wins when conditions overlap. This differs from the final plan's expiry-based Red/Yellow/Green rules and separate Blue low-stock alert.

## 2. MySQL tables, columns, keys, and relationships

Source: database/groupmate_clean_setup.sql, including the barcode/sales ALTER statements at the end. The listed schema below is the effective schema after those statements.

| Table | Columns | Primary/other keys | Declared relationships |
|---|---|---|---|
| ai_prediction | pred_id BIGINT; store_id BIGINT nullable; product_id BIGINT nullable; pred_date DATE; pred_target_period VARCHAR(20); pred_confidence_score DECIMAL(5,2); pred_risk_lvl VARCHAR(20); pred_suggested_action VARCHAR(255) | PK pred_id; indexes FK_AI_store(store_id), FK_AI_product(product_id). pred_id is not AUTO_INCREMENT. | store_id references store.store_id. product_id is indexed but has no declared FK. |
| analysis | analysis_id BIGINT; store_id BIGINT; product_id BIGINT; analysis_days_idle INT; analysis_status INT; analysis_recomm VARCHAR(255); analysis_last_analyzed TIMESTAMP | PK analysis_id; indexes analysis_FKIndex1(product_id), analysis_FKIndex2(store_id), IFK_product_id(product_id), IFK_store_id(store_id). analysis_id is not AUTO_INCREMENT. | store_id references store.store_id. product_id is indexed but has no declared FK. No use of this table was found in the PHP/Python source. |
| barangay | brgy_id BIGINT AUTO_INCREMENT; brgy_name VARCHAR(200); mun_id BIGINT | PK brgy_id; index mun_id | No declared FK to municipality. |
| credential | cre_id BIGINT AUTO_INCREMENT; users_id BIGINT; cre_username VARCHAR(100); cre_password VARCHAR(255); cre_status TINYINT | PK cre_id; indexes credential_FKIndex1(users_id), IFK_users_id(users_id). No unique index on cre_username. | No declared FK to users. |
| municipality | mun_id BIGINT AUTO_INCREMENT; prov_id BIGINT; mun_name VARCHAR(200); mun_zipcode INT | PK mun_id; index prov_id | No declared FK to province. |
| product | product_id BIGINT AUTO_INCREMENT; store_id BIGINT; product_name VARCHAR(100); product_barcode VARCHAR(50) NULL; product_quantity INT; product_date_added DATE | PK product_id; indexes product_FKIndex1(store_id), IFK_store_id(store_id); unique index uq_store_product_barcode(store_id, product_barcode), added by the SQL tail. | store_id references store.store_id. Nullable barcodes can repeat as NULL under MySQL unique-index behavior. |
| province | prov_id BIGINT AUTO_INCREMENT; prov_name VARCHAR(200) | PK prov_id | No outbound FK. |
| sales | sales_id BIGINT AUTO_INCREMENT after the SQL tail; store_id BIGINT; product_id BIGINT; sale_quantity INT; sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP | PK sales_id; indexes sales_FKIndex1(product_id), sales_FKIndex2(store_id), IFK_product_id(product_id), IFK_store_id(store_id), idx_sales_store_product_date(store_id, product_id, sale_date). | product_id references product.product_id; store_id references store.store_id. The two independent FKs do not enforce that a product belongs to the same store as the sale. |
| stock_movement | movement_id INT AUTO_INCREMENT; product_id BIGINT; store_id BIGINT; users_id BIGINT; movement_type ENUM(add, reduce, return); quantity INT; previous_quantity INT; new_quantity INT; notes VARCHAR(255); movement_date DATETIME | PK movement_id; indexes idx_sm_product(product_id), idx_sm_store(store_id), idx_sm_users(users_id) | store_id references store.store_id; users_id references users.users_id. product_id has an index but no declared FK. |
| store | store_id BIGINT AUTO_INCREMENT; store_name VARCHAR(50); store_location VARCHAR(50) | PK store_id | No outbound FK. The dump seeds one row: Demo Store. |
| users | users_id BIGINT AUTO_INCREMENT; store_id BIGINT; users_fname VARCHAR(50); users_mname VARCHAR(50); users_lname VARCHAR(50); users_sname VARCHAR(20); barangay_id INT; users_role ENUM(owner, clerk), default clerk | PK users_id; indexes users_FKIndex1(store_id), IFK_store_id(store_id) | No declared FK to store or barangay. |

The dump also defines these stored procedures: SpCheckUsernameExists_Sababan, SpCreateCredential_Herminado, SpCreateStore_Sababan, SpCreateUser_Herminado, SpGetUserByUsername_Sababan, SpSelectBrgyByMuni_Fabia, SpSelectMuniByPro_Lago, SpSelectProducts_valenzuela, SpSelectProv_Maramag, and SpSelectStores_Fabia. No trigger definitions were found. The procedure and lookup tables support current PHP account/location flows, while the migrated API should move query logic into SQLAlchemy repositories/services rather than depend on MySQL stored procedures.

The included SQL has geography seed rows and one Demo Store. It explicitly distributes no user/credential rows and has empty product, sales, stock_movement, ai_prediction, and analysis sections. It cannot validate existing production row counts or production data quality.

## 3. PHP page/endpoint to FastAPI endpoint map

The target is static HTML/CSS/JS pages that call JSON APIs with fetch. The API routes below are proposed routes; preserve the current behavior first, then add the final-plan features in their specified phases. Page rendering should be static and is not itself a FastAPI data endpoint.

| PHP file | New endpoint | Method | Notes |
|---|---|---|---|
| 1st prog/php/auth/login.php | /api/auth/login | POST | Accept credentials, verify bcrypt hash, establish secure session/cookie, return/redirect to dashboard. |
| 1st prog/php/auth/logout.php | /api/auth/logout | POST | Invalidate session and cookie. Keep CSRF protection for browser-authenticated mutations. |
| 1st prog/php/auth/register.php | /api/auth/register | POST | Validate fields, unique username, location/store choice, hash password, create store/user/credential in one transaction. Decide first-owner policy before implementation. |
| 1st prog/php/config/db_connection.example.php | No endpoint; replace with backend/app/core/config.py and backend/app/db/session.py | — | Read MySQL URL/secrets from .env; never expose DB settings to the browser. The real db_connection.php is intentionally omitted. |
| 1st prog/php/dashboard.php | /api/dashboard/summary | GET | Return store-scoped totals and chart series. Later dashboard also calls /api/ai/items and /api/ai/evaluation as specified by the plan. |
| 1st prog/php/inventory/inventory_tracking.php | /api/stock and /api/stock/movements | GET | Preserve current-stock view, filters, owner all-store scope, ordering, and pagination. Add batch view after stock batches exist. |
| 1st prog/php/inventory/low_stock.php | /api/ai/items?status=blue | GET | Current page is a placeholder. Blue classification depends on forecast demand during supplier lead time plus safety stock. |
| 1st prog/php/inventory/reduce_stock.php | /api/products/{product_id}/stock-adjustments | POST | Compatibility alias for action=decrease; retain validation and movement audit behavior. |
| 1st prog/php/locations/get_barangays.php | /api/locations/barangays?municipality_id={id} | GET | Return barangay IDs and names for the registration selector. |
| 1st prog/php/locations/get_municipalities.php | /api/locations/municipalities?province_id={id} | GET | Return municipalities for a province. |
| 1st prog/php/locations/get_provinces.php | /api/locations/provinces | GET | Return province list. |
| 1st prog/php/locations/get_stores.php | /api/locations/stores | GET | Return stores for registration. Review whether only active/public stores should be listed. |
| 1st prog/php/products/add_product.php | /api/products | POST | Create product and initial stock. New plan-required product fields and optional initial batch belong here once schema is extended. |
| 1st prog/php/products/adjust_stock.php | /api/products/{product_id}/stock-adjustments and /api/products/{product_id} | POST and DELETE | POST covers increase/decrease with audit record; DELETE retains owner-only guard and history-retention rule. |
| 1st prog/php/products/product_management.php | /api/products | GET | Return the role/store-scoped product list and history-retention flags. Use the POST/adjustment/delete routes above for mutations. |
| 1st prog/php/reports/reports.php | /api/reports/summary and /api/ai/evaluation | GET | Current page is a placeholder. Evaluation endpoint is explicitly required by the final plan; decide any additional sales-report filters during implementation. |
| 1st prog/php/sales/record_sale.php | /api/sales | POST | Preserve atomic checkout, barcode lookup, validation, and sales/stock audit. Extend for cart, discounts, transaction grouping, and batch deduction. |
| 1st prog/php/sales/sales_transactions.php | /api/sales, /api/products/lookup?barcode={code}, and /api/ai/items | GET | Return recent sales, best sellers, product lookup/scan preview, and AI monitoring data. |
| 1st prog/php/users/user_management.php | /api/users | GET | Current page is a placeholder. Role-changing operations need explicit owner/IT-admin authorization and are not defined in current PHP. |

Additional target-plan endpoints not backed by a current PHP file: GET /api/ai/items, GET /api/ai/items/{id}, GET /api/ai/evaluation, and POST /api/assistant/ask. For stock-in batches and CSV upload, add POST /api/products/{id}/batches and POST /api/imports/products or /api/imports/sales (final route names to settle with the frontend). Unknown barcodes should return a clear registration action as required by the plan.

## 4. Current V and D formula implementation

The final plan describes the previous formula-based system as V = ΣSales / n and D = S / V, where S is stock, V is average sales per observation period, and D estimates how many periods of stock remain. The plan does not define the sampling interval or exactly what n counts.

Neither V nor D is implemented in the supplied code. A repository-wide source search found no velocity/duration variable or equivalent calculation. The actual current monitoring path is:

1. 1st prog/php/sales/sales_transactions.php queries product quantity S, product age, sold_30d, sold_90d, and days_since_last_sale. sold_30d and sold_90d are sums of sale_quantity over rolling timestamp windows. days_since_last_sale is sent but is not used by the Python classifier.
2. The PHP page sends those signals to POST http://127.0.0.1:8000/analyze.
3. 1st prog/fastapi-service/main.py sets forecast_sales_30d = sold_30d. It does not divide by days, periods, or n; it simply repeats the previous 30-day unit total as the next 30-day forecast.
4. It reports projected_stock_30d = max(0, S - forecast_sales_30d) and shortage_30d = max(0, forecast_sales_30d - S), then applies the age/sales if/else rules in section 1 above.

Therefore, the documented V/D rules describe prior or intended logic, but the supplied current implementation is a 30-day carry-forward baseline. Use the moving-average definition in the final plan for the fallback, and settle the training/sampling interval and treatment of zero-sales days before implementation.

## 5. Data readiness

| Required data | Status | Evidence and gap |
|---|---|---|
| Sales recorded per item with date and time | Available in schema; no rows in supplied clean dump | sales stores product_id, sale_quantity, and sale_date TIMESTAMP, plus store_id and an index by store/product/date. It records no unit price or discount. The current SQL groups per product and uses rolling windows. |
| Expiry date stored per stock batch | Not available | No expiry column and no batch table. product_date_added is a product-level DATE and is not an expiry date or a delivery date. |
| Supplier lead time and reorder level | Not available | No supplier table, supplier lead-time column, product reorder-level column, or safety-stock value. The dashboard's <=10 quantity check is hard-coded. |
| Product category and unit | Not available | product has no category or unit field. |
| Product selling price | Not available | No product price or sale line price is stored. |
| Sale discount/PWD/Senior Citizen data | Not available | No sale transaction header or discount/customer eligibility fields. |
| Historical CSV/Excel sales and product import | Not available | No import code or import files found. The clean demo SQL contains no sales/products to seed history. |
| User/store/location data | Partial | Schema and registration procedures exist; location tables are seeded and one demo store exists, but the SQL intentionally has no user/credential rows. Live DB data is NOT FOUND. |

## 6. Database changes needed for the final plan

Use additive, versioned migrations against a backup of the actual target database. Do not run the clean setup SQL over the owner's working database. Existing aggregate stock and dates cannot be used to infer batch expiry; legacy stock should remain explicitly “expiry unknown” until the owner supplies real batch data. Do not fabricate expiry dates.

| Proposed change | Reason |
|---|---|
| Extend product with category, unit, unit_price, reorder_level, supplier_lead_time_days, and safety_stock_units (or a documented store-level default). Add a supplier table and product-supplier relation only if a product can have multiple suppliers. | Required product registration fields and the plan's Blue rule need item category/unit/price and reorder/lead-time/safety-stock inputs. |
| Add stock_batch with batch_id, product_id, received_quantity, remaining_quantity, received_at, expiry_date, and suitable indexes/FKs. Add batch_id to stock movements or a stock_batch_movement/allocation table. | Each delivery needs its own expiry and received date. Sales must deduct against nearest expiry first and preserve which batch was consumed. |
| Group POS checkout rows with a sale_transaction header (store, user, checkout time, totals, discount type/value) and link existing sales item rows to it; add unit sale price and per-line discount where needed. | Current sales rows are item/quantity events but cannot represent a multi-item checkout, price, total, or PWD/Senior discount. A transaction header preserves checkout semantics. |
| Add a batch-allocation relation between each sold item and one or more batches; keep the allocation/movement and sale in one DB transaction. | A single sale quantity can consume several expiry batches. The audit data must show exactly which batch stock was deducted from. |
| Extend ai_prediction or add forecast_run and item_forecast tables for forecast horizon, median/low/high demand, baseline result, expiry horizon, U, status, model name/version, and generated_at/cache time. Add a product FK and store/product/time indexes. | Current ai_prediction only stores risk/action/confidence/period metadata, has no numeric forecast, and product_id has no declared FK. The dashboard needs cached per-item forecast ranges and model comparison. |
| Add database constraints and indexes after checking existing data: unique credential.cre_username, FK credential.users_id, and appropriate FKs for users.store_id/barangay_id, barangay.mun_id, municipality.prov_id, stock_movement.product_id, analysis.product_id, and ai_prediction.product_id. Consider a composite product/store relationship for sales and movement consistency. | Current schema has duplicate non-unique indexes but omits several logical FKs and username uniqueness. Constraints reduce orphan rows and duplicate-account races; existing data must be checked before applying them. |
| Make ai_prediction.pred_id and analysis.analysis_id generated keys if those tables remain in use, or replace their legacy design through a migration. | Both primary keys are declared without AUTO_INCREMENT in the supplied setup, and the current PHP does not insert rows into them. |
| Add optional import_job/import_error tables only if import previews, retry/audit history, or resumable large imports are required. The required evaluation_results.csv can remain a versioned output artifact as stated in the plan. | The plan requires CSV import and evaluation output but does not require storing those files in MySQL. Persist import metadata only if the product workflow needs it. |

Before applying constraints, inspect the actual working database for duplicates/orphans. The clean demo SQL cannot prove that the live database has compatible data or exactly these schema versions.

## 7. Proposed FastAPI project structure

Keep the static frontend separate from the Python API while preserving the current visual design and user flows.

- 1st prog/frontend/index.html
- 1st prog/frontend/pages/ (dashboard, products, stock history, sales, low stock, reports, users)
- 1st prog/frontend/css/style.css
- 1st prog/frontend/js/ (api client, auth, dashboard, products, stock, sales, assistant)
- 1st prog/backend/app/main.py
- 1st prog/backend/app/core/ (settings, security, sessions, role checks)
- 1st prog/backend/app/db/ (SQLAlchemy engine/session, models, migrations)
- 1st prog/backend/app/schemas/ (Pydantic request/response schemas)
- 1st prog/backend/app/api/routes/ (auth, locations, products, batches, stock, sales, dashboard, users, reports, ai, assistant, imports)
- 1st prog/backend/app/repositories/ (parameterized SQLAlchemy data access)
- 1st prog/backend/app/services/ (auth, inventory, checkout, imports, forecasting, classification, evaluation, retrieval/assistant)
- 1st prog/backend/app/tasks/ (nightly forecasts and cache refresh)
- 1st prog/backend/tests/ (pytest coverage specified in build phase 9)
- 1st prog/notebooks/chronos_evaluation.ipynb
- 1st prog/.env.example, requirements.txt, README.md

The running .env and database credentials stay local and out of version control. Keep the PHP source until the replacement passes the parity and acceptance checks in the plan.

## 8. Build phases, split into small testable steps

These steps preserve the final plan's order. Each step should have a stated acceptance check and a commit before moving to the next phase. No steps below have been performed in this audit.

### Phase 1 — Backup and Git setup

1. Obtain a fresh backup of the actual working code and full live MySQL schema/data/routines; verify it can be identified separately from the clean demo SQL.
2. Initialize or inspect Git history, add/verify ignores for local DB credentials, .env, generated model files, and private SQL exports.
3. Create .env.example and move only local secrets/configuration to .env; verify the secret file is ignored.
4. Create the migration branch and record the pre-migration baseline commit. The supplied ZIP contains no .git directory, so history must come from the real repository or be initialized from the chosen baseline.

### Phase 2 — Audit

1. Review this MIGRATION_PLAN.md against the actual source and live database, correcting any schema/data differences.
2. Confirm feature scope, route map, permissions, and unresolved questions below.
3. Record approval before changing application code. This audit deliverable is the only project change requested at this point.

### Phase 3 — Chronos evaluation notebook

1. Select a usable historical sales dataset and document its source, date coverage, item coverage, and missing-data rules.
2. Prepare per-item daily series, including zero-sale days, and reserve the final 28 days for the holdout.
3. Compare Chronos-Bolt, the moving-average baseline, and Prophet using MAE, RMSE, and WAPE; do not report MAPE.
4. Evaluate Red classification with precision, recall, F1, and confusion matrix; use paired t-test and Wilcoxon signed-rank test on per-item errors.
5. Save actual measured outputs to evaluation_results.csv and review whether the model adds value before integrating it. If the private history is unavailable, record that evaluation is blocked rather than inventing results.

### Phase 4 — Migrate PHP to FastAPI, one feature at a time

1. Create FastAPI app/configuration, SQLAlchemy connection/session, Pydantic schemas, health endpoint, and safe .env loading; verify a read-only connection to the intended MySQL database.
2. Port registration/login/logout and location lookups; verify bcrypt, session lifecycle, role checks, validation, and registration transaction.
3. Port product list/create/delete and stock adjustments against the current schema; preserve owner/clerk access, barcode uniqueness, quantity bounds, CSRF/session security, and movement audit.
4. Port stock history with its filters, page boundaries, store scoping, and owner all-store view; compare representative results with PHP.
5. Port sales lookup/recording with transaction locks and stock history; compare quantities and timestamps with the PHP flow.
6. Port dashboard queries and make all tenant/store scoping explicit; compare chart series and totals with PHP using the same database snapshot.
7. Port the existing 30-day baseline temporarily if needed for parity; keep it clearly labeled as a baseline until the Chronos phase is accepted.
8. Convert PHP-included .html templates into static pages and fetch/populate them from APIs. Verify direct page loads, navigation, empty states, and error states.
9. Keep PHP available until each migrated flow has passed its agreed parity check.

### Phase 5 — Scanner, POS, stock-in, and CSV import

1. Add barcode lookup with USB keyboard scanner support, manual search, and the planned unknown-barcode registration prompt; verify matching is store-scoped.
2. Add camera fallback with html5-qrcode and test permission denied, camera unavailable, and successful scan behavior.
3. Build a multi-item cart and checkout; store item prices and PWD/Senior Citizen discount details, validate totals, and write the checkout atomically.
4. Add stock-in as one batch per delivery with received date and expiry date; verify aggregate product quantity stays consistent with remaining batch quantities.
5. Deduct from the nearest-expiry eligible batch first; verify audit rows and handling of insufficient, expired, or missing-expiry stock after the owner chooses those policies.
6. Add CSV/Excel import preview, row-level validation, product matching by barcode, sales history import by date/barcode/qty_sold, and clear duplicate/idempotency behavior.

### Phase 6 — Hybrid AI engine

1. Add daily item-level history extraction and moving-average baseline; label items under 28 days as Not enough data.
2. Load amazon/chronos-bolt-small once at FastAPI startup; check memory, disk, startup time, and inference time on the intended machine.
3. Forecast through the nearest expiry with a maximum 60-day horizon; for later expiries, extend with the forecast's average daily demand.
4. Implement the final Red/Yellow/Green rules and independent Blue low-stock rule using batch expiry, supplier lead time, safety stock, and demand forecast.
5. Cache per-item results and add nightly plus on-demand refresh with GET /api/ai/items, GET /api/ai/items/{id}, and GET /api/ai/evaluation.
6. Verify no-sales, short history, missing expiry, zero stock, expired batches, no batches, and forecast-horizon boundary cases against approved rule expectations.

### Phase 7 — RAG assistant

1. Choose Groq or local Ollama and keep tokens/configuration in .env.
2. Retrieve only the relevant item's status, stock, expiry, forecast, recent sales, and suggested actions from current structured data.
3. Add POST /api/assistant/ask with a response containing both the answer and the retrieved data used.
4. Verify answers stay within retrieved facts, missing data is stated plainly, and provider failures do not break dashboard/checkout.

### Phase 8 — Dashboard

1. Add summary cards and a store-scoped item table with Red/Yellow/Green/Blue badges.
2. Add forecast chart with low/high range and item detail view.
3. Add model comparison/evaluation metrics sourced from actual evaluation_results.csv results.
4. Add assistant chat and verify empty/loading/error states and responsive layout.

### Phase 9 — Testing and acceptance

1. Add pytest coverage for barcode lookup, checkout with discounts, nearest-expiry stock deduction, CSV import, classification rules, and assistant retrieval.
2. Cover unknown barcode, no sales, under-28-day history, no expiry date, zero stock, expired batches, duplicate import, insufficient stock, and store/role boundaries.
3. Verify migration/backfill and rollback against a disposable copy of the real database.
4. Measure API response time against the plan's under-2-second target on the intended local hardware, separately recording model cold-start/inference behavior.
5. Compare migrated feature outputs against PHP before retiring any PHP route; keep actual evaluation numbers and test results, with no fabricated metrics.

## 9. Risks and questions to resolve

1. **Which database is the migration target?** The ZIP contains only inventory_group_demo, a clean demo with no operational rows. The live inventory_restore_20260930 export and its schema/data are NOT FOUND here. Please identify the actual target backup before any schema or data migration.
2. **What is the parity baseline?** Should “same functionality” mean parity with the source features that are implemented, or should the migration also complete the final-plan placeholders (reports, user tools, camera scanner, low-stock workflow) as part of the target? The final plan points toward the latter, but the current reports/user pages are placeholders.
3. **How is the first store owner created?** Current registration always creates a clerk. The setup guide asks for a manual database update. Decide whether the first registered account is owner, an invite/bootstrap token is required, or an IT Admin provisions roles.
4. **What permissions should Store Owner/Admin, Staff/Cashier, and IT Admin have?** The current database only supports owner/clerk. Define whether IT Admin can cross stores and how cross-store access is audited.
5. **What is n and the time unit for V?** The final plan says V = ΣSales / n but does not state whether n is days, weeks, or non-zero-sales observations. Confirm the moving-average window and whether zero-sales days count.
6. **How should overlapping alerts work?** The plan says Red/Yellow/Green classification and a separate Blue low-stock alert. Confirm whether Blue can appear alongside any expiry-risk color, and the precedence for no-sales/under-28-day data.
7. **What should happen when stock has no known expiry, is already expired, or has quantity zero?** The database cannot infer a real expiry for existing stock. Confirm whether such inventory is excluded from expiry risk, shown as unknown, blocked from sale when expired, or handled another way.
8. **How should historical imports match products and transactions?** Define barcode normalization, duplicate handling, date/time timezone, invalid rows, and whether prices/discounts are available in the real CSV/Excel sources.
9. **What discount policy and checkout fields are required?** The plan names PWD/Senior Citizen discount but does not specify the calculation, validation, transaction fields, or whether customer identity is stored.
10. **Can intended machines run Chronos locally?** The plan specifies at least 8 GB RAM, 16 GB recommended, and about 60 GB free storage. Confirm target device(s), expected item count, and whether CPU-only inference is acceptable; also choose Groq versus Ollama for the assistant.
11. **What behavior should unknown barcodes trigger?** The plan says prompt registration. Confirm whether staff can create a draft product or only an owner can register it.
12. **Which time zone should sales and nightly forecasts use?** Sales are stored as MySQL TIMESTAMP without an app-level timezone policy. Define the store-local date boundary and the nightly run time.
13. **Can the existing business data satisfy the evaluation?** The clean SQL has no sales history. A Chronos-versus-baseline report requires actual timestamped item sales covering a holdout period; otherwise evaluation is blocked until a suitable dataset is supplied.
14. **Will the live schema match this clean demo schema?** The setup notes state the current owner's database and older snapshots differ. Confirm migrations against the real schema, including stored procedures and any manually applied changes, before coding.

