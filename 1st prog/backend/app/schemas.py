from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    middle_name: str = Field(default="", max_length=50)
    suffix_name: str = Field(default="", max_length=20)
    last_name: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str
    barangay_id: int = Field(gt=0)
    store_option: Literal["existing", "new"]
    store_id: int | None = None
    custom_store_name: str | None = Field(default=None, max_length=50)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=128)


class ProductCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=100)
    product_barcode: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_-]{3,50}$")
    product_quantity: int = Field(ge=0, le=1000000)
    category: str = Field(default="Other", max_length=40)
    unit: str = Field(default="pieces", max_length=30)
    price: float = Field(default=0, ge=0)
    reorder_level: int = Field(default=0, ge=0)
    supplier_lead_time_days: int = Field(default=0, ge=0, le=365)
    safety_stock_units: int = Field(default=0, ge=0)
    expiry_date: date | None = None


class StockAdjustment(BaseModel):
    action: Literal["increase", "decrease"]
    quantity: int = Field(gt=0, le=1000000)
    notes: str = Field(default="", max_length=180)
    expiry_date: date | None = None


class SaleLine(BaseModel):
    product_id: int | None = Field(default=None, gt=0)
    barcode: str | None = Field(default=None, min_length=3, max_length=50)
    quantity: int = Field(gt=0, le=10000)


class CheckoutRequest(BaseModel):
    items: list[SaleLine] = Field(min_length=1, max_length=100)
    discount_type: Literal["none", "pwd", "senior"] = "none"
    discount_reference: str = Field(default="", max_length=40)


class AssistantRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    product_id: int | None = Field(default=None, gt=0)


class CsvImportResult(BaseModel):
    model_config = ConfigDict(extra="allow")
