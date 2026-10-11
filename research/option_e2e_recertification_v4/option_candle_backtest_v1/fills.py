from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .models import CandleBacktestConfig


@dataclass(frozen=True)
class Fill:
    status: str
    reference_price: float | None
    fill_price: float | None
    quantity: int
    source: str
    reason: str | None = None


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def adverse_price(price: float, *, action: str, slippage_bps: float) -> float:
    multiplier = 1.0 + float(slippage_bps) / 10_000.0 if action == "BUY" else 1.0 - float(slippage_bps) / 10_000.0
    return round(max(float(price) * multiplier, 0.01), 2)


def validate_ohlcv_bar(row: pd.Series) -> None:
    values = {name: _number(row.get(name)) for name in ("open", "high", "low", "close")}
    if any(value is None or value <= 0 for value in values.values()):
        raise ValueError("invalid_ohlc_price")
    if values["low"] > values["high"]:
        raise ValueError("invalid_ohlc_geometry")
    if values["high"] < max(values["open"], values["close"]):
        raise ValueError("invalid_ohlc_geometry")
    if values["low"] > min(values["open"], values["close"]):
        raise ValueError("invalid_ohlc_geometry")
    volume = _number(row.get("volume"))
    if volume is None or volume < 0:
        raise ValueError("invalid_volume")


def _fillable_quantity(row: pd.Series, config: CandleBacktestConfig) -> int:
    volume = _number(row.get("volume")) or 0.0
    if volume <= 0:
        return 0
    capacity = max(int(volume * float(config.max_volume_participation)), 1)
    return min(int(config.quantity), capacity)


def entry_fill(row: pd.Series, config: CandleBacktestConfig) -> Fill:
    validate_ohlcv_bar(row)
    quantity = _fillable_quantity(row, config)
    if quantity <= 0:
        return Fill("NOFILL", None, None, 0, "next_bar_open", "zero_reported_volume")
    reference = float(row["open"])
    return Fill(
        "FILLED" if quantity == config.quantity else "PARTIAL",
        reference,
        adverse_price(reference, action="BUY", slippage_bps=config.entry_slippage_bps),
        quantity,
        "next_bar_open_plus_adverse_slippage",
    )


def long_exit_trigger(
    row: pd.Series,
    *,
    target_price: float,
    stop_price: float,
    config: CandleBacktestConfig,
) -> tuple[str | None, float | None, bool]:
    validate_ohlcv_bar(row)
    opened = float(row["open"])
    high = float(row["high"])
    low = float(row["low"])
    stop_hit = low <= float(stop_price)
    target_hit = high >= float(target_price)
    ambiguous = stop_hit and target_hit

    if ambiguous and config.intrabar_conflict_policy == "STOP_FIRST":
        return "STOP_HIT", min(opened, float(stop_price)), True
    if stop_hit:
        return "STOP_HIT", min(opened, float(stop_price)), False
    if target_hit:
        # Do not award favourable gap improvement when only OHLC is available.
        return "TARGET_HIT", float(target_price), False
    return None, None, False


def exit_fill(
    row: pd.Series,
    *,
    reference_price: float,
    quantity: int,
    reason: str,
    config: CandleBacktestConfig,
) -> Fill:
    validate_ohlcv_bar(row)
    if quantity <= 0:
        return Fill("NOFILL", None, None, 0, "option_candle", "invalid_quantity")
    return Fill(
        "FILLED",
        float(reference_price),
        adverse_price(float(reference_price), action="SELL", slippage_bps=config.exit_slippage_bps),
        int(quantity),
        f"{reason.lower()}_candle_reference_plus_adverse_slippage",
    )
