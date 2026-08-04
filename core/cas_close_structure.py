"""NSE Closing Auction Session (CAS) phase and shadow-evidence helpers.

This module is deliberately read-only. It classifies the post-15:15 market
process and summarizes replay evidence, but it never emits an executable trade
candidate or calls a broker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from math import isfinite
from typing import Iterable, Mapping, Sequence

CAS_EFFECTIVE_DATE = date(2026, 8, 3)

PHASE_PRE_OPEN = "PRE_OPEN"
PHASE_NORMAL_CONTINUOUS = "NORMAL_CONTINUOUS"
PHASE_CAS_REFERENCE_TRANSITION = "CAS_REFERENCE_TRANSITION"
PHASE_CAS_ORDER_DISCOVERY = "CAS_ORDER_DISCOVERY"
PHASE_CAS_RANDOM_CLOSE_WINDOW = "CAS_RANDOM_CLOSE_WINDOW"
PHASE_CAS_MATCHING = "CAS_MATCHING"
PHASE_DERIVATIVE_CONVERGENCE = "DERIVATIVE_CONVERGENCE"
PHASE_POST_CLOSE = "POST_CLOSE"

NSE_CASH_SEGMENTS = frozenset({"NSE_EQ", "NSE_CASH", "CASH", "CM"})
NSE_DERIVATIVE_SEGMENTS = frozenset({"NSE_FNO", "NFO", "FNO", "DERIVATIVES"})
CAS_PHASES = frozenset(
    {
        PHASE_CAS_REFERENCE_TRANSITION,
        PHASE_CAS_ORDER_DISCOVERY,
        PHASE_CAS_RANDOM_CLOSE_WINDOW,
        PHASE_CAS_MATCHING,
        PHASE_DERIVATIVE_CONVERGENCE,
    }
)


def _as_ist_naive(value: datetime) -> datetime:
    """Return an IST wall-clock datetime without importing project time helpers."""
    if value.tzinfo is None:
        return value
    try:
        from zoneinfo import ZoneInfo

        return value.astimezone(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    except Exception:
        return value.replace(tzinfo=None)


def classify_nse_close_phase(current_time: datetime, *, segment: str = "NSE_FNO") -> str:
    """Classify the NSE close process using the rule effective 2026-08-03.

    Before the effective date, the legacy 15:30 close is preserved so historical
    replay does not silently acquire the new regime.
    """
    now = _as_ist_naive(current_time)
    seg = str(segment or "NSE_FNO").strip().upper()
    t = now.time()

    if t < time(9, 15):
        return PHASE_PRE_OPEN

    if now.date() < CAS_EFFECTIVE_DATE:
        return PHASE_NORMAL_CONTINUOUS if t < time(15, 30) else PHASE_POST_CLOSE

    if seg not in NSE_CASH_SEGMENTS and seg not in NSE_DERIVATIVE_SEGMENTS:
        return PHASE_NORMAL_CONTINUOUS

    if t < time(15, 15):
        return PHASE_NORMAL_CONTINUOUS
    if t < time(15, 20):
        return PHASE_CAS_REFERENCE_TRANSITION
    if t < time(15, 25):
        return PHASE_CAS_ORDER_DISCOVERY
    if t < time(15, 30):
        return PHASE_CAS_RANDOM_CLOSE_WINDOW
    if t < time(15, 35):
        return PHASE_CAS_MATCHING

    if seg in NSE_DERIVATIVE_SEGMENTS and t < time(15, 40):
        return PHASE_DERIVATIVE_CONVERGENCE
    return PHASE_POST_CLOSE


def normal_strategy_entry_allowed(
    current_time: datetime,
    *,
    segment: str = "NSE_FNO",
    last_normal_entry: time = time(15, 5),
) -> bool:
    """Allow ordinary strategies only before the frozen pre-CAS cutoff."""
    now = _as_ist_naive(current_time)
    return (
        classify_nse_close_phase(now, segment=segment) == PHASE_NORMAL_CONTINUOUS
        and now.time() <= last_normal_entry
    )


def normal_strategy_position_may_cross_cas(
    current_time: datetime,
    *,
    planned_hold_minutes: float,
) -> bool:
    """Return True when an ordinary position's planned hold reaches 15:15."""
    now = _as_ist_naive(current_time)
    if not isfinite(float(planned_hold_minutes)) or float(planned_hold_minutes) < 0:
        raise ValueError("planned_hold_minutes_must_be_non_negative")
    seconds_to_cas = (
        datetime.combine(now.date(), time(15, 15)) - now
    ).total_seconds()
    return seconds_to_cas <= float(planned_hold_minutes) * 60.0


def _finite_returns(values: Iterable[float]) -> list[float]:
    out: list[float] = []
    for value in values:
        try:
            numeric = float(value)
        except Exception:
            continue
        if isfinite(numeric):
            out.append(numeric)
    return out


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        raise ValueError("median_requires_values")
    middle = count // 2
    if count % 2:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2.0)


@dataclass(frozen=True)
class CASCloseObservation:
    session_date: str
    pre_match_index: float
    matched_index: float
    index_jump_points: float
    index_jump_bps: float
    constituent_count: int
    positive_constituents: int
    negative_constituents: int
    unchanged_constituents: int
    breadth_positive_ratio: float
    equal_weight_mean_return_pct: float
    median_return_pct: float
    top_three_absolute_move_share: float
    evidence_class: str
    diagnostic_direction: str
    indicative_revision_series_available: bool
    auction_imbalance_available: bool
    futures_available: bool
    real_option_contracts_available: bool
    authority: str = "SHADOW_ADVISORY_ONLY"
    execution_eligible: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_cas_close_observation(
    *,
    session_date: str,
    pre_match_index: float,
    matched_index: float,
    constituent_returns_pct: Sequence[float],
    indicative_revision_series_available: bool = False,
    auction_imbalance_available: bool = False,
    futures_available: bool = False,
    real_option_contracts_available: bool = False,
) -> CASCloseObservation:
    """Summarize final CAS repricing without making a trading claim."""
    pre = float(pre_match_index)
    matched = float(matched_index)
    if not (isfinite(pre) and isfinite(matched) and pre > 0):
        raise ValueError("valid_positive_index_prices_required")

    returns = _finite_returns(constituent_returns_pct)
    if not returns:
        raise ValueError("constituent_returns_required")

    positives = sum(value > 0 for value in returns)
    negatives = sum(value < 0 for value in returns)
    unchanged = len(returns) - positives - negatives
    mean_return = sum(returns) / len(returns)
    median_return = _median(returns)
    absolute = sorted((abs(value) for value in returns), reverse=True)
    absolute_total = sum(absolute)
    top_three_share = sum(absolute[:3]) / absolute_total if absolute_total > 0 else 0.0

    jump_points = matched - pre
    jump_bps = jump_points / pre * 10_000.0
    breadth_positive = positives / len(returns)

    same_direction_breadth = (
        breadth_positive if jump_points > 0 else negatives / len(returns)
    )
    median_confirms = (
        median_return > 0 if jump_points > 0 else median_return < 0
    )
    if abs(jump_bps) < 1.0:
        evidence_class = "NO_MATERIAL_AUCTION_REPRICING"
        diagnostic_direction = "NEUTRAL"
    elif same_direction_breadth >= 0.75 and median_confirms and top_three_share <= 0.30:
        evidence_class = "BROAD_AUCTION_REPRICING"
        diagnostic_direction = "UP" if jump_points > 0 else "DOWN"
    elif top_three_share > 0.50:
        evidence_class = "CONCENTRATED_AUCTION_REPRICING"
        diagnostic_direction = "UP" if jump_points > 0 else "DOWN"
    else:
        evidence_class = "MIXED_AUCTION_REPRICING"
        diagnostic_direction = "UP" if jump_points > 0 else "DOWN"

    return CASCloseObservation(
        session_date=str(session_date),
        pre_match_index=pre,
        matched_index=matched,
        index_jump_points=jump_points,
        index_jump_bps=jump_bps,
        constituent_count=len(returns),
        positive_constituents=positives,
        negative_constituents=negatives,
        unchanged_constituents=unchanged,
        breadth_positive_ratio=breadth_positive,
        equal_weight_mean_return_pct=mean_return,
        median_return_pct=median_return,
        top_three_absolute_move_share=top_three_share,
        evidence_class=evidence_class,
        diagnostic_direction=diagnostic_direction,
        indicative_revision_series_available=bool(indicative_revision_series_available),
        auction_imbalance_available=bool(auction_imbalance_available),
        futures_available=bool(futures_available),
        real_option_contracts_available=bool(real_option_contracts_available),
    )


def cas_research_readiness(observation: CASCloseObservation) -> Mapping[str, object]:
    """Return bounded research readiness; never execution eligibility."""
    missing: list[str] = []
    if not observation.indicative_revision_series_available:
        missing.append("INDICATIVE_CLOSE_REVISION_SERIES")
    if not observation.auction_imbalance_available:
        missing.append("AUCTION_ORDER_IMBALANCE")
    if not observation.futures_available:
        missing.append("NIFTY_FUTURES_PATH")
    if not observation.real_option_contracts_available:
        missing.append("REAL_NIFTY_OPTION_CONTRACT_PATH")

    return {
        "final_auction_structure_observable": True,
        "predictive_cas_hypothesis_testable": not missing,
        "missing_authoritative_inputs": missing,
        "authority": "SHADOW_ADVISORY_ONLY",
        "execution_eligible": False,
        "verdict": (
            "FINAL_AUCTION_STRUCTURE_OBSERVED_PREDICTIVE_EDGE_BLOCKED"
            if missing
            else "CAS_PREDICTIVE_RESEARCH_INPUTS_AVAILABLE"
        ),
    }


__all__ = [
    "CAS_EFFECTIVE_DATE",
    "CAS_PHASES",
    "CASCloseObservation",
    "PHASE_CAS_MATCHING",
    "PHASE_CAS_ORDER_DISCOVERY",
    "PHASE_CAS_RANDOM_CLOSE_WINDOW",
    "PHASE_CAS_REFERENCE_TRANSITION",
    "PHASE_DERIVATIVE_CONVERGENCE",
    "PHASE_NORMAL_CONTINUOUS",
    "PHASE_POST_CLOSE",
    "build_cas_close_observation",
    "cas_research_readiness",
    "classify_nse_close_phase",
    "normal_strategy_entry_allowed",
    "normal_strategy_position_may_cross_cas",
]
