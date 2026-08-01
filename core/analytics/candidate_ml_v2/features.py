from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import SAFETY_CONTRACT, SCHEMA_VERSION
from .dataset import coerce_epoch_ms, safe_float


_TS_KEYS = ("ts_epoch_ms", "timestamp_epoch_ms", "ts_epoch", "timestamp", "time_ms")
_PRICE_KEYS = ("mark_price", "ltp", "close", "price")


def _timestamp(row: Mapping[str, Any]) -> int | None:
    for key in _TS_KEYS:
        ts = coerce_epoch_ms(row.get(key))
        if ts is not None:
            return ts
    return None


def _value(row: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _causal_rows(rows: Sequence[Mapping[str, Any]], decision_ts_ms: int, source: str) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        ts = _timestamp(row)
        if ts is None:
            raise ValueError(f"{source}_timestamp_missing:{index}")
        if ts > decision_ts_ms:
            raise ValueError(f"{source}_future_row:{ts}>{decision_ts_ms}")
        normalized.append({**dict(row), "__ts_ms": int(ts)})
    normalized.sort(key=lambda item: int(item["__ts_ms"]))
    return normalized


def _return(rows: Sequence[Mapping[str, Any]], lag: int, keys: Sequence[str] = _PRICE_KEYS) -> float | None:
    if len(rows) <= lag:
        return None
    latest = _value(rows[-1], keys)
    previous = _value(rows[-1 - lag], keys)
    if latest is None or previous in (None, 0):
        return None
    return float(latest / previous - 1.0)


def _relative_latest(rows: Sequence[Mapping[str, Any]], key: str, window: int = 20) -> float | None:
    values = [safe_float(row.get(key)) for row in rows[-(window + 1):]]
    numeric = [value for value in values if value is not None]
    if len(numeric) < 3:
        return None
    latest = numeric[-1]
    baseline = float(np.mean(numeric[:-1]))
    if baseline == 0:
        return None
    return float(latest / baseline)


def _weighted_snapshot(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    if not rows:
        return {
            "breadth_up_1": None,
            "breadth_down_1": None,
            "breadth_mean_ret1": None,
            "breadth_dispersion": None,
            "leadership_concentration": None,
        }
    returns: list[float] = []
    weights: list[float] = []
    weighted_abs: list[float] = []
    for row in rows:
        ret = _value(row, ("return_1", "ret1", "return"))
        if ret is None:
            continue
        weight = safe_float(row.get("weight"))
        weight = abs(weight) if weight not in (None, 0) else 1.0
        returns.append(ret)
        weights.append(weight)
        weighted_abs.append(abs(ret) * weight)
    if not returns:
        return {
            "breadth_up_1": None,
            "breadth_down_1": None,
            "breadth_mean_ret1": None,
            "breadth_dispersion": None,
            "leadership_concentration": None,
        }
    ret_arr = np.asarray(returns, dtype=float)
    weight_arr = np.asarray(weights, dtype=float)
    total_weight = float(np.sum(weight_arr))
    mean = float(np.average(ret_arr, weights=weight_arr))
    variance = float(np.average((ret_arr - mean) ** 2, weights=weight_arr))
    gross = float(np.sum(weighted_abs))
    concentration = float(sum(sorted(weighted_abs, reverse=True)[:3]) / gross) if gross > 0 else 0.0
    return {
        "breadth_up_1": float(np.sum(weight_arr[ret_arr > 0]) / total_weight),
        "breadth_down_1": float(np.sum(weight_arr[ret_arr < 0]) / total_weight),
        "breadth_mean_ret1": mean,
        "breadth_dispersion": math.sqrt(max(0.0, variance)),
        "leadership_concentration": concentration,
    }


def _constituent_features(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["__ts_ms"])].append(row)
    timestamps = sorted(grouped)
    latest = _weighted_snapshot(grouped[timestamps[-1]]) if timestamps else _weighted_snapshot([])
    previous = _weighted_snapshot(grouped[timestamps[-2]]) if len(timestamps) > 1 else _weighted_snapshot([])
    latest["breadth_acceleration"] = (
        float(latest["breadth_mean_ret1"] - previous["breadth_mean_ret1"])
        if latest["breadth_mean_ret1"] is not None and previous["breadth_mean_ret1"] is not None
        else None
    )
    latest["constituent_count"] = float(len(grouped[timestamps[-1]])) if timestamps else 0.0
    return latest


def build_temporal_candidate_features(
    *,
    decision_ts_epoch_ms: int,
    underlying_rows: Sequence[Mapping[str, Any]],
    constituent_rows: Sequence[Mapping[str, Any]],
    option_rows: Sequence[Mapping[str, Any]],
    mirror_option_rows: Sequence[Mapping[str, Any]] = (),
    expiry_ts_epoch_ms: int | None = None,
) -> dict[str, Any]:
    decision_ts = coerce_epoch_ms(decision_ts_epoch_ms)
    if decision_ts is None:
        raise ValueError("decision_timestamp_invalid")
    underlying = _causal_rows(underlying_rows, decision_ts, "underlying")
    constituents = _causal_rows(constituent_rows, decision_ts, "constituent")
    option = _causal_rows(option_rows, decision_ts, "option")
    mirror = _causal_rows(mirror_option_rows, decision_ts, "mirror_option") if mirror_option_rows else []
    if len(underlying) < 6:
        raise ValueError("underlying_history_insufficient")
    if len(option) < 6:
        raise ValueError("option_history_insufficient")
    if not constituents:
        raise ValueError("constituent_history_missing")

    latest_underlying = underlying[-1]
    latest_option = option[-1]
    close = _value(latest_underlying, ("close", "ltp", "price"))
    vwap = _value(latest_underlying, ("vwap",))
    atr = _value(latest_underlying, ("atr", "atr_14"))
    distance_vwap_atr = float((close - vwap) / atr) if close is not None and vwap is not None and atr not in (None, 0) else None

    bid = safe_float(latest_option.get("bid"))
    ask = safe_float(latest_option.get("ask"))
    mid = (bid + ask) / 2.0 if bid is not None and ask is not None and ask >= bid else None
    spread_pct = float((ask - bid) / mid * 100.0) if mid not in (None, 0) and bid is not None and ask is not None else None
    quote_age_sec = float(max(0, decision_ts - int(latest_option["__ts_ms"])) / 1000.0)

    constituent = _constituent_features(constituents)
    underlying_return_1 = _return(underlying, 1, ("close", "ltp", "price"))
    option_return_1 = _return(option, 1)
    mirror_return_1 = _return(mirror, 1) if mirror else None
    expiry_ts = coerce_epoch_ms(expiry_ts_epoch_ms) if expiry_ts_epoch_ms is not None else None
    minutes_to_expiry = float((expiry_ts - decision_ts) / 60000.0) if expiry_ts is not None else None
    if minutes_to_expiry is not None and minutes_to_expiry < 0:
        raise ValueError("expiry_precedes_decision")

    source_max_ts = max(
        int(underlying[-1]["__ts_ms"]),
        int(option[-1]["__ts_ms"]),
        max(int(row["__ts_ms"]) for row in constituents),
        int(mirror[-1]["__ts_ms"]) if mirror else 0,
    )
    if source_max_ts > decision_ts:
        raise ValueError("feature_source_after_decision")

    underlying_returns = [
        value
        for value in (
            _return(underlying[:index], 1, ("close", "ltp", "price"))
            for index in range(2, len(underlying) + 1)
        )
        if value is not None
    ][-5:]
    previous_option_return = _return(option[:-1], 1)
    latest_option_oi = safe_float(option[-1].get("oi"))
    previous_option_oi = safe_float(option[-2].get("oi"))

    return {
        "schema_version": SCHEMA_VERSION,
        "decision_ts_epoch_ms": decision_ts,
        "feature_cutoff_ts_epoch_ms": decision_ts,
        "feature_source_max_ts_epoch_ms": source_max_ts,
        "underlying_return_1": underlying_return_1,
        "underlying_return_3": _return(underlying, 3, ("close", "ltp", "price")),
        "underlying_return_5": _return(underlying, 5, ("close", "ltp", "price")),
        "underlying_volatility_5": float(np.std(underlying_returns, ddof=0)),
        "distance_from_vwap_atr": distance_vwap_atr,
        "relative_volume": _relative_latest(underlying, "volume"),
        "spread_pct": spread_pct,
        "quote_age_sec": quote_age_sec,
        "option_return_1": option_return_1,
        "option_return_3": _return(option, 3),
        "option_return_5": _return(option, 5),
        "option_acceleration": (
            float(option_return_1 - previous_option_return)
            if option_return_1 is not None and previous_option_return is not None
            else None
        ),
        "option_relative_volume": _relative_latest(option, "volume"),
        "option_oi_change_1": (
            float(latest_option_oi / previous_option_oi - 1.0)
            if latest_option_oi is not None and previous_option_oi not in (None, 0)
            else None
        ),
        "mirror_option_return_1": mirror_return_1,
        "option_mirror_response_gap": (
            float(option_return_1 - mirror_return_1)
            if option_return_1 is not None and mirror_return_1 is not None
            else None
        ),
        "index_breadth_divergence": (
            float(underlying_return_1 - constituent["breadth_mean_ret1"])
            if underlying_return_1 is not None and constituent["breadth_mean_ret1"] is not None
            else None
        ),
        "minutes_to_expiry": minutes_to_expiry,
        "decision_hour_utc": float(datetime.fromtimestamp(decision_ts / 1000.0, tz=timezone.utc).hour),
        **constituent,
        **SAFETY_CONTRACT,
    }
