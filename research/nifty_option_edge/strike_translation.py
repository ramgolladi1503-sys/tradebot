from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd

from .contracts import (
    CLAIM_BOUNDARY_OPTION_APPROX,
    CLAIM_BOUNDARY_OPTION_REALIZED,
    ForecastSignal,
    StrikeRankingConfig,
)

_REQUIRED_CHAIN = {"strike", "option_type", "bid", "ask", "delta"}


@dataclass(frozen=True)
class StrikeDecision:
    status: str
    reason: str
    selected: dict[str, object] | None
    candidates: tuple[dict[str, object], ...]
    claim_boundary: str = CLAIM_BOUNDARY_OPTION_APPROX

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _atm_strike(spot: float, step: float) -> float:
    return math.floor((float(spot) / step) + 0.5) * step


def _moneyness(option_type: str, relative_steps: int) -> str:
    if relative_steps == 0:
        return "ATM"
    if option_type == "CE":
        return "ITM" if relative_steps < 0 else "OTM"
    return "ITM" if relative_steps > 0 else "OTM"


def _no_trade(reason: str) -> StrikeDecision:
    return StrikeDecision(status="NO_TRADE", reason=reason, selected=None, candidates=())


def rank_option_strikes(
    option_chain: pd.DataFrame,
    *,
    spot: float,
    forecast: ForecastSignal,
    config: StrikeRankingConfig | None = None,
) -> StrikeDecision:
    """Translate a directional magnitude forecast into research-only strike candidates.

    This is not realized option P&L. It uses current quotes/Greeks to estimate how
    ATM/ITM/OTM candidates may respond to the forecasted underlying move and refuses
    to select a strike when estimated net premium change is non-positive.
    """

    config = config or StrikeRankingConfig()
    if not np.isfinite(float(spot)) or float(spot) <= 0:
        raise ValueError("spot must be finite and positive")
    if forecast.direction == "NO_TRADE":
        return _no_trade("forecast_no_trade")
    if forecast.probability_direction < config.min_probability_direction:
        return _no_trade("forecast_probability_below_threshold")
    if abs(forecast.expected_spot_move_points) < config.min_abs_expected_spot_move_points:
        return _no_trade("forecast_move_below_threshold")

    missing = _REQUIRED_CHAIN.difference(option_chain.columns)
    if missing:
        return _no_trade(f"option_chain_missing_required_fields:{','.join(sorted(missing))}")

    desired_type = "CE" if forecast.direction == "BULLISH" else "PE"
    atm = _atm_strike(float(spot), config.strike_step)
    records: list[dict[str, object]] = []

    for row in option_chain.to_dict(orient="records"):
        option_type = str(row.get("option_type", "")).upper().strip()
        if option_type != desired_type:
            continue
        try:
            strike = float(row["strike"])
            bid = float(row["bid"])
            ask = float(row["ask"])
            delta = float(row["delta"])
        except (TypeError, ValueError, KeyError):
            continue
        if not all(np.isfinite(v) for v in (strike, bid, ask, delta)):
            continue
        if bid < 0 or ask <= 0 or ask < bid:
            continue
        if abs(delta) < config.min_abs_delta or abs(delta) > config.max_abs_delta:
            continue

        relative_steps_float = (strike - atm) / config.strike_step
        relative_steps = int(round(relative_steps_float))
        if not math.isclose(relative_steps_float, relative_steps, abs_tol=1e-6):
            continue
        if abs(relative_steps) > config.max_moneyness_steps:
            continue

        mid = (bid + ask) / 2.0
        if mid <= 0:
            continue
        spread_points = ask - bid
        spread_pct = (spread_points / mid) * 100.0
        if spread_pct > config.max_spread_pct:
            continue

        volume = float(row.get("volume", 0.0) or 0.0)
        open_interest = float(row.get("open_interest", 0.0) or 0.0)
        if volume < config.min_volume or open_interest < config.min_open_interest:
            continue

        gamma = row.get("gamma")
        theta = row.get("theta")
        try:
            gamma_value = float(gamma) if gamma is not None else 0.0
        except (TypeError, ValueError):
            gamma_value = 0.0
        try:
            theta_value = float(theta) if theta is not None else 0.0
        except (TypeError, ValueError):
            theta_value = 0.0
        if not np.isfinite(gamma_value):
            gamma_value = 0.0
        if not np.isfinite(theta_value):
            theta_value = 0.0

        move = float(forecast.expected_spot_move_points)
        horizon_days = float(forecast.horizon_minutes) / (24.0 * 60.0)
        delta_component = delta * move
        gamma_component = 0.5 * gamma_value * (move**2)
        theta_component = theta_value * horizon_days
        expected_gross_change = delta_component + gamma_component + theta_component

        friction = (
            spread_points
            + config.slippage_points_round_trip
            + config.fees_points_round_trip
        )
        expected_net_change = expected_gross_change - friction
        expected_return_pct = (expected_net_change / ask) * 100.0
        delta_only_breakeven_move = (
            friction / abs(delta) if abs(delta) > 0 else float("inf")
        )

        candidate: dict[str, object] = {
            "instrument": row.get("instrument"),
            "expiry": row.get("expiry"),
            "strike": strike,
            "option_type": option_type,
            "atm_strike": atm,
            "relative_steps": relative_steps,
            "moneyness": _moneyness(option_type, relative_steps),
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread_points": spread_points,
            "spread_pct": spread_pct,
            "delta": delta,
            "gamma": gamma_value,
            "theta": theta_value,
            "greek_approximation": "DELTA_GAMMA_THETA" if gamma is not None and theta is not None else "DELTA_WITH_MISSING_GREEKS_ZEROED",
            "expected_spot_move_points": move,
            "expected_gross_premium_change": expected_gross_change,
            "expected_net_premium_points": expected_net_change,
            "expected_return_pct": expected_return_pct,
            "delta_only_breakeven_spot_move_points": delta_only_breakeven_move,
            "volume": volume,
            "open_interest": open_interest,
            "claim_boundary": CLAIM_BOUNDARY_OPTION_APPROX,
        }
        if config.lot_size is not None:
            candidate["expected_net_rupees_per_lot"] = expected_net_change * config.lot_size
        records.append(candidate)

    if not records:
        return _no_trade("no_eligible_strikes")

    metric = config.ranking_metric
    ranked = sorted(
        records,
        key=lambda item: (
            float(item[metric]),
            -float(item["spread_pct"]),
            float(item["open_interest"]),
        ),
        reverse=True,
    )
    best = ranked[0]
    if float(best["expected_net_premium_points"]) <= 0:
        return StrikeDecision(
            status="NO_TRADE",
            reason="best_strike_expected_net_non_positive",
            selected=None,
            candidates=tuple(ranked),
        )

    return StrikeDecision(
        status="SELECTED",
        reason="positive_expected_option_translation",
        selected=best,
        candidates=tuple(ranked),
    )


def realized_option_pnl_from_quotes(
    *,
    entry_ask: float,
    exit_bid: float,
    slippage_points_round_trip: float = 0.0,
    fees_points_round_trip: float = 0.0,
    lot_size: int | None = None,
) -> dict[str, float | int | str | None]:
    """Conservative realized long-option P&L from real entry ask and exit bid quotes."""

    numbers = (entry_ask, exit_bid, slippage_points_round_trip, fees_points_round_trip)
    if not all(np.isfinite(float(value)) for value in numbers):
        raise ValueError("quote/cost values must be finite")
    if entry_ask <= 0 or exit_bid < 0:
        raise ValueError("invalid entry/exit quote")
    if slippage_points_round_trip < 0 or fees_points_round_trip < 0:
        raise ValueError("cost assumptions cannot be negative")
    if lot_size is not None and lot_size <= 0:
        raise ValueError("lot_size must be positive when supplied")

    pnl_points = (
        float(exit_bid)
        - float(entry_ask)
        - float(slippage_points_round_trip)
        - float(fees_points_round_trip)
    )
    return_pct = (pnl_points / float(entry_ask)) * 100.0
    return {
        "entry_ask": float(entry_ask),
        "exit_bid": float(exit_bid),
        "pnl_points": pnl_points,
        "return_pct": return_pct,
        "lot_size": lot_size,
        "pnl_rupees_per_lot": pnl_points * lot_size if lot_size is not None else None,
        "claim_boundary": CLAIM_BOUNDARY_OPTION_REALIZED,
    }
