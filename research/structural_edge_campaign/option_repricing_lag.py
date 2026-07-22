from __future__ import annotations

import math
from typing import Any, Mapping

import pandas as pd

from .option_repricing_lag_math import (
    Black76Greeks,
    RepricingLagError,
    black76_greeks,
    black76_price,
    canonical_hash,
    implied_volatility_black76,
)

_SIGNAL_FIELDS = (
    "timestamp",
    "option_type",
    "futures_price",
    "previous_futures_price",
    "strike",
    "years_to_expiry",
    "option_bid",
    "option_ask",
    "previous_option_bid",
    "previous_option_ask",
    "reference_iv",
    "previous_reference_iv",
    "elapsed_seconds",
    "futures_return_z",
    "futures_ofi_z",
    "option_trade_imbalance_z",
    "option_book_imbalance",
    "front_iv_shock_z",
    "quote_age_ms",
    "dte",
    "is_expiry_day",
    "event_blocked",
    "tick_size",
)


def _mid(bid: Any, ask: Any, *, field: str) -> float:
    try:
        bid_value = float(bid)
        ask_value = float(ask)
    except (TypeError, ValueError) as exc:
        raise RepricingLagError(f"{field} quotes are invalid") from exc
    if (
        not math.isfinite(bid_value)
        or not math.isfinite(ask_value)
        or bid_value <= 0
        or ask_value <= 0
        or bid_value > ask_value
    ):
        raise RepricingLagError(f"{field} quotes are non-executable")
    return (bid_value + ask_value) / 2.0


def _time_in_window(timestamp: Any, start: str, end: str) -> bool:
    value = pd.Timestamp(timestamp)
    if value.tzinfo is None:
        value = value.tz_localize("Asia/Kolkata")
    else:
        value = value.tz_convert("Asia/Kolkata")
    current = value.strftime("%H:%M")
    return start <= current <= end


def evaluate_repricing_snapshot(
    snapshot: Mapping[str, Any],
    *,
    specification: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> dict[str, Any]:
    missing = [field for field in _SIGNAL_FIELDS if field not in snapshot]
    if missing:
        raise RepricingLagError(
            f"repricing snapshot missing required fields: {missing}"
        )
    signal = specification["signal"]
    contract_selection = specification["contract_selection"]
    option_type = str(snapshot["option_type"]).upper().strip()
    if option_type not in {"CE", "PE"}:
        raise RepricingLagError("option_type must be CE or PE")

    reasons: list[str] = []
    if not _time_in_window(
        snapshot["timestamp"],
        specification["entry_window"]["start"],
        specification["entry_window"]["end"],
    ):
        reasons.append("OUTSIDE_ENTRY_WINDOW")
    dte = int(snapshot["dte"])
    if not (
        int(contract_selection["dte_min"])
        <= dte
        <= int(contract_selection["dte_max"])
    ):
        reasons.append("DTE_OUTSIDE_FROZEN_RANGE")
    if bool(snapshot["is_expiry_day"]):
        reasons.append("EXPIRY_DAY_EXCLUDED")
    if bool(snapshot["event_blocked"]):
        reasons.append("SCHEDULED_EVENT_BLOCK")
    if float(snapshot["quote_age_ms"]) > float(signal["max_quote_age_ms"]):
        reasons.append("STALE_OPTION_QUOTE")

    futures_z = float(snapshot["futures_return_z"])
    impulse_threshold = float(variant["futures_return_z_min"])
    direction = 1 if futures_z > 0 else -1 if futures_z < 0 else 0
    expected_type = (
        str(contract_selection["bullish_option_type"])
        if direction > 0
        else str(contract_selection["bearish_option_type"])
    )
    if direction == 0 or abs(futures_z) < impulse_threshold:
        reasons.append("FUTURES_IMPULSE_TOO_WEAK")
    if option_type != expected_type:
        reasons.append("OPTION_TYPE_DOES_NOT_MATCH_IMPULSE")

    futures_ofi_z = float(snapshot["futures_ofi_z"])
    if direction == 0 or direction * futures_ofi_z < float(
        signal["futures_ofi_z_min"]
    ):
        reasons.append("FUTURES_OFI_NOT_CONFIRMED")
    if float(snapshot["option_trade_imbalance_z"]) < float(
        signal["option_trade_imbalance_z_min"]
    ):
        reasons.append("OPTION_BUY_FLOW_NOT_CONFIRMED")
    if float(snapshot["option_book_imbalance"]) < float(
        signal["option_book_imbalance_min"]
    ):
        reasons.append("OPTION_BOOK_NOT_SUPPORTIVE")

    previous_mid = _mid(
        snapshot["previous_option_bid"],
        snapshot["previous_option_ask"],
        field="previous option",
    )
    current_mid = _mid(
        snapshot["option_bid"],
        snapshot["option_ask"],
        field="current option",
    )
    current_spread = float(snapshot["option_ask"]) - float(
        snapshot["option_bid"]
    )
    risk_free_rate = float(signal["risk_free_rate"])
    previous_iv = implied_volatility_black76(
        option_type,
        previous_mid,
        float(snapshot["previous_futures_price"]),
        float(snapshot["strike"]),
        float(snapshot["years_to_expiry"]),
        risk_free_rate,
    )
    greeks = black76_greeks(
        option_type,
        float(snapshot["previous_futures_price"]),
        float(snapshot["strike"]),
        float(snapshot["years_to_expiry"]),
        previous_iv,
        risk_free_rate,
    )
    absolute_delta = abs(float(greeks.delta))
    if not (
        float(contract_selection["absolute_delta_min"])
        <= absolute_delta
        <= float(contract_selection["absolute_delta_max"])
    ):
        reasons.append("DELTA_OUTSIDE_FROZEN_BAND")
    futures_change = float(snapshot["futures_price"]) - float(
        snapshot["previous_futures_price"]
    )
    reference_iv_change = float(snapshot["reference_iv"]) - float(
        snapshot["previous_reference_iv"]
    )
    elapsed_years = float(snapshot["elapsed_seconds"]) / (
        365.0 * 24.0 * 60.0 * 60.0
    )
    fair_change = (
        greeks.delta * futures_change
        + 0.5 * greeks.gamma * futures_change * futures_change
        + greeks.vega * reference_iv_change
        + greeks.theta_per_year * elapsed_years
    )
    observed_change = current_mid - previous_mid
    lag = fair_change - observed_change
    tick_size = float(snapshot["tick_size"])
    cost_buffer = (
        float(variant["repricing_lag_spread_multiple"]) * current_spread
        + float(signal["round_trip_cost_points"])
        + float(signal["max_chase_ticks"]) * tick_size
    )
    if lag <= cost_buffer:
        reasons.append("REPRICING_LAG_NOT_EXECUTABLE")
    if (
        float(snapshot["front_iv_shock_z"])
        > float(signal["max_front_iv_shock_z"])
        and lag <= cost_buffer
    ):
        reasons.append("FRONT_IV_ALREADY_REPRICED")

    signal_ok = not reasons
    entry_ask = float(snapshot["option_ask"])
    entry_limit = entry_ask + float(signal["max_chase_ticks"]) * tick_size
    economic = {
        "hypothesis_id": specification["hypothesis_id"],
        "family": specification["family"],
        "variant": dict(variant),
        "direction": "BULLISH" if direction > 0 else "BEARISH",
        "option_type": option_type,
        "execution_side": "BUY",
        "pricing_model": signal["pricing_model"],
    }
    return {
        "signal": signal_ok,
        "rejection_reasons": sorted(set(reasons)),
        "direction": economic["direction"],
        "option_type": option_type,
        "entry_quote_side": "ASK",
        "entry_limit": entry_limit if signal_ok else None,
        "max_hold_minutes": int(signal["max_hold_minutes"]),
        "fair_option_change": float(fair_change),
        "observed_option_change": float(observed_change),
        "repricing_lag": float(lag),
        "required_cost_buffer": float(cost_buffer),
        "previous_implied_volatility": float(previous_iv),
        "delta": greeks.delta,
        "gamma": greeks.gamma,
        "vega": greeks.vega,
        "theta_per_year": greeks.theta_per_year,
        "candidate_rule_hash": canonical_hash(economic),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def signal_fingerprint(
    snapshots: pd.DataFrame,
    *,
    specification: Mapping[str, Any],
    variant: Mapping[str, Any],
) -> str:
    rows: list[dict[str, Any]] = []
    for record in snapshots.to_dict(orient="records"):
        result = evaluate_repricing_snapshot(
            record,
            specification=specification,
            variant=variant,
        )
        rows.append(
            {
                "timestamp": str(record["timestamp"]),
                "signal": result["signal"],
                "candidate_rule_hash": result["candidate_rule_hash"],
                "rejection_reasons": result["rejection_reasons"],
            }
        )
    return canonical_hash(rows)


from .option_repricing_lag_data import (
    audit_data_readiness,
    development_evidence_from_readiness,
    file_sha256,
    load_table,
)


__all__ = [
    "Black76Greeks",
    "RepricingLagError",
    "audit_data_readiness",
    "black76_greeks",
    "black76_price",
    "canonical_hash",
    "development_evidence_from_readiness",
    "evaluate_repricing_snapshot",
    "file_sha256",
    "implied_volatility_black76",
    "load_table",
    "signal_fingerprint",
]
