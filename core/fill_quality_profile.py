from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.analytics.time_of_day import bucket_for_timestamp_ms


@dataclass(frozen=True)
class FillQualityProfile:
    symbol: str
    premium_bucket: str
    liquidity_bucket: str
    time_bucket: str
    trade_count: int
    filled_trade_count: int
    fill_rate: float
    expected_fill_deviation: float | None
    slippage_multiplier: float | None
    fill_confidence: float
    avg_reference_deviation: float | None
    reference_trade_count: int

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "fill_rate",
            "expected_fill_deviation",
            "slippage_multiplier",
            "fill_confidence",
            "avg_reference_deviation",
        ):
            value = payload.get(key)
            if value is not None:
                payload[key] = round(float(value), 6)
        return payload


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    except Exception:
        return None


def _coerce_epoch_ms(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw >= 10_000_000_000:
            return int(raw)
        return int(raw * 1000.0)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _coerce_epoch_ms(float(text))
    except Exception:
        pass
    try:
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp() * 1000.0)
    except Exception:
        return None


def premium_bucket(price: Any) -> str:
    px = _safe_float(price)
    if px is None or px <= 0:
        return "UNKNOWN"
    if px <= 20.0:
        return "MICRO"
    if px <= 80.0:
        return "LOW"
    if px <= 200.0:
        return "MID"
    return "HIGH"


def liquidity_bucket(
    *,
    volume: Any = None,
    spread_pct: Any = None,
    depth_best: Any = None,
    qty: Any = None,
    quote_ok: Any = True,
) -> str:
    spread = _safe_float(spread_pct)
    vol = _safe_float(volume)
    depth = _safe_float(depth_best)
    size = max(_safe_float(qty) or 1.0, 1.0)
    depth_ratio = None if depth in (None, 0.0) else size / max(depth, 1.0)

    if bool(quote_ok) is False:
        return "THIN"
    if spread is not None and spread >= 0.02:
        return "THIN"
    if depth_ratio is not None and depth_ratio > 1.5:
        return "THIN"
    if vol is not None and vol < 500.0:
        return "THIN"
    if (
        (spread is None or spread <= 0.005)
        and (depth_ratio is None or depth_ratio <= 0.75)
        and (vol is None or vol >= 2500.0)
    ):
        return "LIQUID"
    if vol is not None and vol >= 5000.0 and (spread is None or spread <= 0.01):
        return "LIQUID"
    return "NORMAL"


def _normalized_time_bucket(ts_epoch_ms: Any, symbol: Any = None) -> str:
    ts_ms = _coerce_epoch_ms(ts_epoch_ms)
    if ts_ms is None:
        return "UNKNOWN"
    return str(bucket_for_timestamp_ms(ts_ms, symbol) or "UNKNOWN").upper()


def normalize_fill_quality_row(row: Mapping[str, Any]) -> dict[str, Any]:
    symbol = str(row.get("symbol") or row.get("underlying") or "UNKNOWN").strip().upper() or "UNKNOWN"
    decision_mid = _safe_float(row.get("decision_mid"))
    if decision_mid is None:
        bid = _safe_float(row.get("decision_bid") if row.get("decision_bid") is not None else row.get("bid"))
        ask = _safe_float(row.get("decision_ask") if row.get("decision_ask") is not None else row.get("ask"))
        if bid is not None and ask is not None:
            decision_mid = (bid + ask) / 2.0
    premium = (
        decision_mid
        or _safe_float(row.get("limit_price"))
        or _safe_float(row.get("entry_price"))
        or _safe_float(row.get("entry"))
        or _safe_float(row.get("fill_price"))
    )
    decision_spread = _safe_float(row.get("decision_spread"))
    if decision_spread is None:
        bid = _safe_float(row.get("decision_bid") if row.get("decision_bid") is not None else row.get("bid"))
        ask = _safe_float(row.get("decision_ask") if row.get("decision_ask") is not None else row.get("ask"))
        if bid is not None and ask is not None and ask >= bid:
            decision_spread = ask - bid
    spread_pct = (
        (_safe_float(row.get("spread_pct")))
        or ((decision_spread / max(decision_mid, 1e-9)) if decision_spread is not None and decision_mid not in (None, 0.0) else None)
    )
    qty = _safe_float(row.get("qty_units"))
    if qty is None or qty <= 0:
        qty = _safe_float(row.get("qty"))
    realized_deviation = _safe_float(row.get("realized_fill_deviation"))
    if realized_deviation is None:
        slippage_vs_mid = _safe_float(row.get("slippage_vs_mid"))
        if slippage_vs_mid is not None:
            realized_deviation = abs(slippage_vs_mid)
        else:
            fill_price = _safe_float(row.get("fill_price"))
            if fill_price is not None and decision_mid is not None:
                realized_deviation = abs(fill_price - decision_mid)
            else:
                realized_deviation = abs(_safe_float(row.get("slippage")) or 0.0) or None
    reference_deviation = _safe_float(row.get("reference_deviation"))
    reference_mode = "provided"
    if reference_deviation is None:
        reference_deviation = _safe_float(row.get("expected_slippage"))
        reference_mode = "expected_slippage"
    if reference_deviation is None and decision_spread is not None:
        reference_deviation = max(decision_spread * 0.5, 0.0)
        reference_mode = "half_spread"
    filled = row.get("filled")
    if filled is None:
        filled = row.get("filled_bool")
    if filled is None:
        filled = _safe_float(row.get("fill_price")) is not None and str(row.get("not_filled_reason") or "").strip() == ""
    return {
        "symbol": symbol,
        "premium_bucket": premium_bucket(premium),
        "liquidity_bucket": liquidity_bucket(
            volume=row.get("volume"),
            spread_pct=spread_pct,
            depth_best=(row.get("depth_best") if row.get("depth_best") is not None else row.get("top_depth_qty")),
            qty=qty,
            quote_ok=row.get("quote_ok", True),
        ),
        "time_bucket": _normalized_time_bucket(
            row.get("timestamp_epoch_ms")
            if row.get("timestamp_epoch_ms") is not None
            else row.get("ts_epoch")
            if row.get("ts_epoch") is not None
            else row.get("timestamp")
            if row.get("timestamp") is not None
            else row.get("ts"),
            symbol=symbol,
        ),
        "filled": bool(filled),
        "realized_fill_deviation": realized_deviation,
        "reference_deviation": reference_deviation,
        "reference_mode": reference_mode,
    }


def build_fill_quality_profiles(rows: Iterable[Mapping[str, Any]]) -> list[FillQualityProfile]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for raw_row in rows or []:
        row = normalize_fill_quality_row(raw_row)
        key = (
            str(row.get("symbol") or "UNKNOWN"),
            str(row.get("premium_bucket") or "UNKNOWN"),
            str(row.get("liquidity_bucket") or "UNKNOWN"),
            str(row.get("time_bucket") or "UNKNOWN"),
        )
        bucket = grouped.setdefault(
            key,
            {
                "trade_count": 0,
                "filled_trade_count": 0,
                "realized_sum": 0.0,
                "realized_count": 0,
                "reference_sum": 0.0,
                "reference_count": 0,
                "multiplier_sum": 0.0,
                "multiplier_count": 0,
            },
        )
        bucket["trade_count"] += 1
        realized = _safe_float(row.get("realized_fill_deviation"))
        reference = _safe_float(row.get("reference_deviation"))
        if bool(row.get("filled")):
            bucket["filled_trade_count"] += 1
        if realized is not None:
            bucket["realized_sum"] += float(realized)
            bucket["realized_count"] += 1
        if reference is not None:
            bucket["reference_sum"] += float(reference)
            bucket["reference_count"] += 1
        if realized is not None and reference is not None and reference > 0:
            bucket["multiplier_sum"] += float(realized) / float(reference)
            bucket["multiplier_count"] += 1

    profiles: list[FillQualityProfile] = []
    for key in sorted(grouped.keys()):
        stats = grouped[key]
        trade_count = int(stats["trade_count"])
        filled_trade_count = int(stats["filled_trade_count"])
        realized_count = int(stats["realized_count"])
        reference_count = int(stats["reference_count"])
        fill_rate = float(filled_trade_count) / max(trade_count, 1)
        avg_realized = (
            float(stats["realized_sum"]) / float(realized_count)
            if realized_count > 0
            else None
        )
        avg_reference = (
            float(stats["reference_sum"]) / float(reference_count)
            if reference_count > 0
            else None
        )
        slippage_multiplier = (
            float(stats["multiplier_sum"]) / float(stats["multiplier_count"])
            if int(stats["multiplier_count"]) > 0
            else (
                (avg_realized / avg_reference)
                if avg_realized is not None and avg_reference not in (None, 0.0)
                else None
            )
        )
        sample_factor = min(1.0, math.sqrt(float(trade_count) / 5.0))
        coverage_factor = min(1.0, float(reference_count) / max(float(trade_count), 1.0))
        fill_confidence = fill_rate * sample_factor * (0.5 + (0.5 * coverage_factor))
        profiles.append(
            FillQualityProfile(
                symbol=key[0],
                premium_bucket=key[1],
                liquidity_bucket=key[2],
                time_bucket=key[3],
                trade_count=trade_count,
                filled_trade_count=filled_trade_count,
                fill_rate=round(fill_rate, 6),
                expected_fill_deviation=(
                    round(float(avg_realized), 6)
                    if avg_realized is not None
                    else round(float(avg_reference), 6)
                    if avg_reference is not None
                    else None
                ),
                slippage_multiplier=round(float(slippage_multiplier), 6) if slippage_multiplier is not None else None,
                fill_confidence=round(float(fill_confidence), 6),
                avg_reference_deviation=round(float(avg_reference), 6) if avg_reference is not None else None,
                reference_trade_count=reference_count,
            )
        )
    return profiles


def profile_rows(profiles: Iterable[FillQualityProfile]) -> list[dict[str, Any]]:
    return [profile.as_dict() for profile in profiles]
