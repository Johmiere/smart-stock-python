from __future__ import annotations

import math


def classify_item(
    stock: int,
    expiry_demand: float | None,
    sold_last_28_days: float,
    lead_time_demand: float,
    safety_stock: int,
) -> dict:
    unknown_expiry = expiry_demand is None
    unsold_at_expiry = None if unknown_expiry else max(0.0, stock - expiry_demand)
    red_by_no_sales = sold_last_28_days <= 0
    red_by_unsold = (
        stock > 0 and not unknown_expiry
        and unsold_at_expiry is not None and unsold_at_expiry >= 0.5 * stock
    )
    if red_by_no_sales:
        risk = "red"
        action = "No sales were recorded in the last 28 days. Consider a discount, bundle, or repositioning."
    elif unknown_expiry:
        risk = "unknown"
        action = "Add a real batch expiry date before assessing expiry risk."
    elif red_by_unsold:
        risk = "red"
        action = "Consider a discount, bundle with a fast-moving item, or reposition the product."
    elif unsold_at_expiry is not None and 0 < unsold_at_expiry < 0.5 * stock:
        risk = "yellow"
        action = "Monitor this batch and consider a light promotion."
    else:
        risk = "green"
        action = "Expected demand should sell through the available stock before expiry."

    low_stock_threshold = lead_time_demand + safety_stock
    low_stock = stock <= low_stock_threshold
    return {
        "status": risk,
        "unsold_at_expiry": None if unsold_at_expiry is None else round(unsold_at_expiry, 2),
        "low_stock": low_stock,
        "low_stock_threshold": round(low_stock_threshold, 2),
        "low_stock_action": (
            f"Reorder approximately {max(0, math.ceil(low_stock_threshold - stock))} units."
            if low_stock else None
        ),
        "suggested_action": action,
    }
