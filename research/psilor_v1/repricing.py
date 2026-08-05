from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .calibration import PSILORError
from .contracts import canonical_hash


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _normal_pdf(value: float) -> float:
    return math.exp(-0.5 * value * value) / math.sqrt(2.0 * math.pi)


def _validate_inputs(
    futures_price: float,
    strike: float,
    years: float,
    volatility: float,
) -> None:
    values = (futures_price, strike, years, volatility)
    if not all(math.isfinite(float(value)) for value in values):
        raise PSILORError("Black-76 inputs must be finite")
    if futures_price <= 0 or strike <= 0 or years <= 0 or volatility <= 0:
        raise PSILORError(
            "Black-76 price, strike, time and volatility must be positive"
        )


def black76_price(
    option_type: str,
    futures_price: float,
    strike: float,
    years_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
) -> float:
    _validate_inputs(futures_price, strike, years_to_expiry, volatility)
    kind = str(option_type).upper()
    if kind not in {"CE", "PE"}:
        raise PSILORError("option_type must be CE or PE")
    sqrt_t = math.sqrt(years_to_expiry)
    d1 = (
        math.log(futures_price / strike)
        + 0.5 * volatility * volatility * years_to_expiry
    ) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    discount = math.exp(-risk_free_rate * years_to_expiry)
    if kind == "CE":
        return discount * (
            futures_price * _normal_cdf(d1) - strike * _normal_cdf(d2)
        )
    return discount * (
        strike * _normal_cdf(-d2) - futures_price * _normal_cdf(-d1)
    )


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    vega: float
    theta_per_year: float


def black76_greeks(
    option_type: str,
    futures_price: float,
    strike: float,
    years_to_expiry: float,
    volatility: float,
    risk_free_rate: float,
) -> Greeks:
    _validate_inputs(futures_price, strike, years_to_expiry, volatility)
    kind = str(option_type).upper()
    if kind not in {"CE", "PE"}:
        raise PSILORError("option_type must be CE or PE")
    sqrt_t = math.sqrt(years_to_expiry)
    d1 = (
        math.log(futures_price / strike)
        + 0.5 * volatility * volatility * years_to_expiry
    ) / (volatility * sqrt_t)
    discount = math.exp(-risk_free_rate * years_to_expiry)
    delta = (
        discount * _normal_cdf(d1)
        if kind == "CE"
        else -discount * _normal_cdf(-d1)
    )
    gamma = discount * _normal_pdf(d1) / (
        futures_price * volatility * sqrt_t
    )
    vega = discount * futures_price * _normal_pdf(d1) * sqrt_t
    now = black76_price(
        kind,
        futures_price,
        strike,
        years_to_expiry,
        volatility,
        risk_free_rate,
    )
    one_day = 1.0 / 365.0
    later = black76_price(
        kind,
        futures_price,
        strike,
        max(years_to_expiry - one_day, 1e-9),
        volatility,
        risk_free_rate,
    )
    theta = (later - now) / one_day
    return Greeks(float(delta), float(gamma), float(vega), float(theta))


def _mid(bid: Any, ask: Any, *, field: str) -> float:
    bid_value = float(bid)
    ask_value = float(ask)
    if (
        not math.isfinite(bid_value)
        or not math.isfinite(ask_value)
        or bid_value <= 0
        or ask_value <= 0
        or bid_value > ask_value
    ):
        raise PSILORError(f"{field} quote is not executable")
    return (bid_value + ask_value) / 2.0


def evaluate_option_repricing_lag(
    snapshot: Mapping[str, Any],
    *,
    specification: Mapping[str, Any],
    expected_option_type: str,
) -> dict[str, Any]:
    required = (
        "option_type",
        "previous_futures_price",
        "futures_price",
        "strike",
        "years_to_expiry",
        "previous_option_bid",
        "previous_option_ask",
        "option_bid",
        "option_ask",
        "previous_reference_iv",
        "reference_iv",
        "elapsed_seconds",
        "quote_age_ms",
        "available_ask_quantity",
        "available_bid_quantity",
        "futures_ofi_z",
        "option_trade_imbalance_z",
        "option_book_imbalance",
        "dte",
        "is_expiry_day",
        "tick_size",
    )
    missing = [field for field in required if field not in snapshot]
    if missing:
        raise PSILORError(f"repricing snapshot missing fields: {missing}")

    option_type = str(snapshot["option_type"]).upper()
    expected = str(expected_option_type).upper()
    if option_type not in {"CE", "PE"} or expected not in {"CE", "PE"}:
        raise PSILORError("option type must be CE or PE")

    rules = specification["repricing"]
    reasons: list[str] = []
    if option_type != expected:
        reasons.append("OPTION_TYPE_MISMATCH")
    if float(snapshot["quote_age_ms"]) > float(rules["max_quote_age_ms"]):
        reasons.append("STALE_QUOTE")
    if int(snapshot["dte"]) < int(rules["dte_min"]) or int(
        snapshot["dte"]
    ) > int(rules["dte_max"]):
        reasons.append("DTE_OUTSIDE_RANGE")
    if bool(snapshot["is_expiry_day"]) and bool(rules["expiry_day_excluded"]):
        reasons.append("EXPIRY_DAY_EXCLUDED")
    if float(snapshot["available_ask_quantity"]) < float(
        rules["minimum_fill_quantity"]
    ):
        reasons.append("INSUFFICIENT_ASK_QUANTITY")
    if float(snapshot["available_bid_quantity"]) <= 0:
        reasons.append("MISSING_BID_EXIT_LIQUIDITY")
    if abs(float(snapshot["futures_ofi_z"])) < float(
        rules["futures_ofi_z_min"]
    ):
        reasons.append("FUTURES_OFI_TOO_WEAK")
    if float(snapshot["option_trade_imbalance_z"]) < float(
        rules["option_trade_imbalance_z_min"]
    ):
        reasons.append("OPTION_BUY_FLOW_TOO_WEAK")
    if float(snapshot["option_book_imbalance"]) < float(
        rules["option_book_imbalance_min"]
    ):
        reasons.append("OPTION_BOOK_NOT_SUPPORTIVE")

    previous_mid = _mid(
        snapshot["previous_option_bid"],
        snapshot["previous_option_ask"],
        field="previous option",
    )
    _mid(snapshot["option_bid"], snapshot["option_ask"], field="current option")
    previous_iv = float(snapshot["previous_reference_iv"])
    current_iv = float(snapshot["reference_iv"])
    greeks = black76_greeks(
        option_type,
        float(snapshot["previous_futures_price"]),
        float(snapshot["strike"]),
        float(snapshot["years_to_expiry"]),
        previous_iv,
        float(rules["risk_free_rate"]),
    )
    absolute_delta = abs(greeks.delta)
    if absolute_delta < float(rules["absolute_delta_min"]) or absolute_delta > float(
        rules["absolute_delta_max"]
    ):
        reasons.append("DELTA_OUTSIDE_RANGE")

    futures_change = float(snapshot["futures_price"]) - float(
        snapshot["previous_futures_price"]
    )
    iv_change = current_iv - previous_iv
    elapsed_years = float(snapshot["elapsed_seconds"]) / (
        365.0 * 24.0 * 60.0 * 60.0
    )
    fair_change = (
        greeks.delta * futures_change
        + 0.5 * greeks.gamma * futures_change * futures_change
        + greeks.vega * iv_change
        + greeks.theta_per_year * elapsed_years
    )
    observed_executable_change = float(snapshot["option_ask"]) - float(
        snapshot["previous_option_ask"]
    )
    lag = fair_change - observed_executable_change
    spread = float(snapshot["option_ask"]) - float(snapshot["option_bid"])
    buffer = (
        float(rules["repricing_lag_spread_multiple"]) * spread
        + float(rules["round_trip_cost_points"])
        + float(rules["max_chase_ticks"]) * float(snapshot["tick_size"])
    )
    if lag <= buffer:
        reasons.append("REPRICING_LAG_NOT_EXECUTABLE")

    economic = {
        "strategy_id": specification["strategy_id"],
        "option_type": option_type,
        "entry_quote_side": "ASK",
        "exit_quote_side": "BID",
        "pricing_model": "BLACK_76_FUTURES",
        "lag_rule": "FAIR_CHANGE_MINUS_EXECUTABLE_ASK_CHANGE",
    }
    return {
        "eligible": not reasons,
        "rejection_reasons": sorted(set(reasons)),
        "entry_quote_side": "ASK",
        "exit_quote_side": "BID",
        "entry_price": float(snapshot["option_ask"]) if not reasons else None,
        "previous_option_mid": previous_mid,
        "fair_option_change": float(fair_change),
        "observed_executable_option_change": float(observed_executable_change),
        "repricing_lag": float(lag),
        "required_cost_buffer": float(buffer),
        "delta": greeks.delta,
        "gamma": greeks.gamma,
        "vega": greeks.vega,
        "theta_per_year": greeks.theta_per_year,
        "candidate_rule_hash": canonical_hash(economic),
        "read_only": True,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }
