from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class ForecastEngine:
    def __init__(self) -> None:
        self.pipeline: Any = None
        self.model_error: str | None = None

    def load(self, enabled: bool, model_id: str, device: str) -> None:
        if not enabled:
            logger.info("Chronos disabled; moving-average fallback is active.")
            return
        try:
            import torch
            from chronos import BaseChronosPipeline

            self.pipeline = BaseChronosPipeline.from_pretrained(
                model_id,
                device_map=device,
                torch_dtype=torch.float32,
            )
            logger.info("Loaded Chronos model %s on %s", model_id, device)
        except Exception as exc:
            self.model_error = str(exc)
            logger.exception("Chronos could not load; fallback forecasts remain available.")

    def forecast(self, daily_sales: list[float], horizon: int) -> dict:
        horizon = max(1, min(int(horizon), 60))
        if daily_sales:
            window = daily_sales[-28:]
            average = sum(window) / max(1, len(window))
        else:
            average = 0.0

        if self.pipeline is not None and len(daily_sales) >= 28:
            try:
                import numpy as np
                import torch

                quantiles, _ = self.pipeline.predict_quantiles(
                    context=[torch.tensor(daily_sales, dtype=torch.float32)],
                    prediction_length=horizon,
                    quantile_levels=[0.1, 0.5, 0.9],
                )
                values = quantiles.detach().cpu().numpy()
                values = np.asarray(values)
                if values.ndim == 3 and values.shape[-1] == 3:
                    low_series, median_series, high_series = values[0, :, 0], values[0, :, 1], values[0, :, 2]
                elif values.ndim == 3 and values.shape[1] == 3:
                    low_series, median_series, high_series = values[0, 0], values[0, 1], values[0, 2]
                else:
                    raise ValueError(f"Unexpected Chronos output shape: {values.shape}")
                return {
                    "method": "chronos-bolt",
                    "daily_rate": max(0.0, float(np.mean(median_series))),
                    "median": max(0.0, float(np.maximum(median_series, 0).sum())),
                    "low": max(0.0, float(np.maximum(low_series, 0).sum())),
                    "high": max(0.0, float(np.maximum(high_series, 0).sum())),
                    "interval_available": True,
                }
            except Exception:
                logger.exception("Chronos inference failed; using the moving-average fallback.")

        median = max(0.0, average * horizon)
        return {
            "method": "moving_average_fallback",
            "daily_rate": max(0.0, average),
            "median": median,
            "low": median,
            "high": median,
            "interval_available": False,
        }


def forecast_for_horizon(engine: ForecastEngine, daily_sales: list[float], horizon_days: int) -> dict:
    if horizon_days <= 0:
        return {
            "method": "not_applicable", "median": 0.0, "low": 0.0,
            "high": 0.0, "daily_rate": 0.0, "interval_available": False,
        }
    capped_days = min(horizon_days, 60)
    result = engine.forecast(daily_sales, capped_days)
    if horizon_days > 60:
        extra_days = horizon_days - 60
        extension = result["daily_rate"] * extra_days
        result["median"] += extension
        result["low"] += extension
        result["high"] += extension
        result["extended_beyond_60_days"] = True
    else:
        result["extended_beyond_60_days"] = False
    result["horizon_days"] = horizon_days
    return result


def daily_series(sales_rows: list[dict], start_date: date, end_date: date) -> list[float]:
    totals: dict[date, float] = {}
    for row in sales_rows:
        value = row.get("sale_date")
        if hasattr(value, "date"):
            value = value.date()
        elif isinstance(value, str):
            value = date.fromisoformat(value[:10])
        if value:
            totals[value] = totals.get(value, 0.0) + float(row.get("sale_quantity") or 0)
    result: list[float] = []
    cursor = start_date
    while cursor <= end_date:
        result.append(totals.get(cursor, 0.0))
        cursor += timedelta(days=1)
    return result
