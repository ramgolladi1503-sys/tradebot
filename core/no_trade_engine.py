"""No-trade engine for the opportunity engine.

This module is pure/read-only for the new opportunity-engine path. It detects
environments where movement candidates should be suppressed or treated as
advisory: chop, stale/fallback quotes, poor liquidity, weak option confirmation,
and conflicting movement evidence.

The legacy ``check_no_trade_conditions`` function is preserved for backwards
compatibility and remains isolated from the new pure assessment layer.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import time
from typing import Any, Iterable, Literal

from core.candidate_pool_quality import analyze_candidate_pool
from core.candidate_exposure import EXPOSURE_BEARISH, EXPOSURE_BULLISH, EXPOSURE_RANGE, normalize_directional_exposure
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.option_confirmation import OptionPressureAssessment, assess_option_pressure
from core.time_utils import now_ist

NoTradeReason = Literal[
    "NO_TRADE_CHOP",
    "NO_TRADE_STALE_FEED",
    "NO_TRADE_FALLBACK_DATA",
    "NO_TRADE_LIQUIDITY",
    "NO_TRADE_WEAK_OPTION_CONFIRMATION",
    "NO_TRADE_CONFLICTING_SIGNALS",
    "NO_TRADE_INCONCLUSIVE_REGIME",
    "NO_TRADE_POOL_CONCENTRATION",
    "NO_TRADE_BASELINE_WEAKNESS",
]

CHOP_THRESHOLD = 0.60
INCONCLUSIVE_THRESHOLD = 0.65
MAX_OPTION_LTP_AGE_SEC = 2.5
MAX_OPTION_SPREAD_PCT = 4.0
MIN_OPTION_DEPTH = 1.0
MIN_DOMINANT_OPTION_SCORE = 0.45
CONFLICTING_SIGNAL_THRESHOLD = 0.45


@dataclass(frozen=True)
class NoTradeSignal:
    reason: NoTradeReason
    severity: float
    message: str
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", clamp_score(self.severity))
        object.__setattr__(self, "reason", str(self.reason).strip().upper())
        object.__setattr__(
            self,
            "blockers",
            tuple(sorted(set(str(item).strip().upper() for item in self.blockers if str(item).strip()))),
        )
        object.__setattr__(
            self,
            "warnings",
            tuple(sorted(set(str(item).strip() for item in self.warnings if str(item).strip()))),
        )
        object.__setattr__(self, "evidence", dict(self.evidence or {}))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        return data


@dataclass(frozen=True)
class NoTradeAssessment:
    schema_version: int
    no_trade: bool
    primary_reason: str
    severity: float
    signals: tuple[NoTradeSignal, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "no_trade": self.no_trade,
            "primary_reason": self.primary_reason,
            "severity": self.severity,
            "signals": [signal.to_dict() for signal in self.signals],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "evidence": dict(self.evidence),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def assess_no_trade(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    candidates: Iterable[StrategyCandidate] | None = None,
    *,
    option_pressure: OptionPressureAssessment | None = None,
) -> NoTradeAssessment:
    """Assess whether the current environment should suppress trade candidates."""

    candidate_tuple = tuple(candidates or ())
    option_assessment = option_pressure or assess_option_pressure(ctx)
    signals: list[NoTradeSignal] = []

    chop_score = safe_float(regime.scores.get("CHOP")) or 0.0
    range_score = safe_float(regime.scores.get("RANGE")) or 0.0
    if chop_score >= CHOP_THRESHOLD:
        signals.append(
            NoTradeSignal(
                reason="NO_TRADE_CHOP",
                severity=chop_score,
                message="High chop regime; raw movement candidates should be suppressed.",
                blockers=("NO_TRADE_CHOP",),
                evidence={"chop_score": chop_score, "range_score": range_score},
            )
        )

    inconclusive_score = safe_float(regime.scores.get("INCONCLUSIVE")) or 0.0
    if inconclusive_score >= INCONCLUSIVE_THRESHOLD:
        signals.append(
            NoTradeSignal(
                reason="NO_TRADE_INCONCLUSIVE_REGIME",
                severity=inconclusive_score,
                message="Regime evidence is inconclusive; avoid forcing a trade explanation.",
                blockers=("NO_TRADE_CHOP",),
                warnings=("inconclusive_regime",),
                evidence={"inconclusive_score": inconclusive_score, "primary_regime": regime.primary_regime},
            )
        )

    age = safe_float(ctx.option_ltp_age_sec)
    if age is None or age > MAX_OPTION_LTP_AGE_SEC:
        signals.append(
            NoTradeSignal(
                reason="NO_TRADE_STALE_FEED",
                severity=1.0 if age is None else clamp_score(age / (MAX_OPTION_LTP_AGE_SEC * 3.0)),
                message="Option quote freshness is missing or stale.",
                blockers=("STALE_OPTION_LTP",),
                warnings=("option_ltp_age_missing" if age is None else "option_ltp_stale",),
                evidence={"option_ltp_age_sec": age, "max_option_ltp_age_sec": MAX_OPTION_LTP_AGE_SEC},
            )
        )

    if ctx.fallback_used or "fallback" in str(ctx.quote_source or "").lower():
        signals.append(
            NoTradeSignal(
                reason="NO_TRADE_FALLBACK_DATA",
                severity=1.0,
                message="Fallback quote data cannot be treated as executable truth.",
                blockers=("FALLBACK_QUOTE_ONLY",),
                evidence={"fallback_used": ctx.fallback_used, "quote_source": ctx.quote_source},
            )
        )

    liquidity_signal = _liquidity_signal(ctx)
    if liquidity_signal is not None:
        signals.append(liquidity_signal)

    dominant_score = max(option_assessment.bullish_score, option_assessment.bearish_score)
    if option_assessment.dominant_direction == "NEUTRAL" or dominant_score < MIN_DOMINANT_OPTION_SCORE:
        signals.append(
            NoTradeSignal(
                reason="NO_TRADE_WEAK_OPTION_CONFIRMATION",
                severity=clamp_score(1.0 - dominant_score),
                message="Option pressure is weak or balanced; do not promote directional candidates.",
                blockers=("OPTION_CONFIRMATION_MISSING",),
                warnings=tuple(option_assessment.warnings),
                evidence={
                    "dominant_direction": option_assessment.dominant_direction,
                    "bullish_score": option_assessment.bullish_score,
                    "bearish_score": option_assessment.bearish_score,
                    "dominance_delta": option_assessment.dominance_delta,
                },
            )
        )

    conflict_signal = _candidate_conflict_signal(candidate_tuple, option_assessment)
    if conflict_signal is not None:
        signals.append(conflict_signal)

    pool_signal = _candidate_pool_quality_signal(candidate_tuple, regime)
    if pool_signal is not None:
        signals.append(pool_signal)

    baseline_signal = _candidate_baseline_signal(candidate_tuple)
    if baseline_signal is not None:
        signals.append(baseline_signal)

    signals_tuple = tuple(sorted(signals, key=lambda item: (-item.severity, item.reason)))
    no_trade = bool(signals_tuple)
    primary_reason = signals_tuple[0].reason if signals_tuple else "TRADE_ALLOWED"
    severity = signals_tuple[0].severity if signals_tuple else 0.0
    blockers = tuple(sorted(set(blocker for signal in signals_tuple for blocker in signal.blockers)))
    warnings = tuple(sorted(set(warning for signal in signals_tuple for warning in signal.warnings)))
    evidence = {
        "primary_regime": regime.primary_regime,
        "regime_scores": dict(regime.scores),
        "candidate_count": len(candidate_tuple),
        "hard_blocked_candidate_count": sum(1 for candidate in candidate_tuple if candidate.has_hard_blocker),
        "option_pressure": option_assessment.to_dict(),
    }
    return NoTradeAssessment(
        schema_version=1,
        no_trade=no_trade,
        primary_reason=primary_reason,
        severity=severity,
        signals=signals_tuple,
        blockers=blockers,
        warnings=warnings,
        evidence=evidence,
    )


def _liquidity_signal(ctx: StrategyContext) -> NoTradeSignal | None:
    ce_spread = safe_float(ctx.ce_spread_pct)
    pe_spread = safe_float(ctx.pe_spread_pct)
    ce_depth = safe_float(ctx.ce_depth)
    pe_depth = safe_float(ctx.pe_depth)
    spread_bad = any(value is None or value > MAX_OPTION_SPREAD_PCT for value in (ce_spread, pe_spread))
    depth_bad = any(value is None or value < MIN_OPTION_DEPTH for value in (ce_depth, pe_depth))
    if not spread_bad and not depth_bad:
        return None
    blockers: list[str] = []
    warnings: list[str] = []
    if spread_bad:
        blockers.append("WIDE_SPREAD")
        if ce_spread is None or pe_spread is None:
            warnings.append("spread_missing")
    if depth_bad:
        blockers.append("MISSING_DEPTH")
        if ce_depth is None or pe_depth is None:
            warnings.append("depth_missing")
    worst_spread = max(value for value in (ce_spread or 0.0, pe_spread or 0.0))
    severity = max(clamp_score(worst_spread / (MAX_OPTION_SPREAD_PCT * 2.0)), 0.65 if depth_bad else 0.0)
    return NoTradeSignal(
        reason="NO_TRADE_LIQUIDITY",
        severity=severity,
        message="Option spread/depth quality is not sufficient for a real opportunity.",
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        evidence={
            "ce_spread_pct": ce_spread,
            "pe_spread_pct": pe_spread,
            "ce_depth": ce_depth,
            "pe_depth": pe_depth,
            "max_option_spread_pct": MAX_OPTION_SPREAD_PCT,
            "min_option_depth": MIN_OPTION_DEPTH,
        },
    )


def _candidate_conflict_signal(
    candidates: tuple[StrategyCandidate, ...],
    option_pressure: OptionPressureAssessment,
) -> NoTradeSignal | None:
    directional = [
        candidate
        for candidate in candidates
        if normalize_directional_exposure(candidate).exposure in {EXPOSURE_BULLISH, EXPOSURE_BEARISH}
    ]
    if not directional:
        return None
    call_count = sum(1 for candidate in directional if candidate.direction == "BUY_CALL")
    put_count = sum(1 for candidate in directional if candidate.direction == "BUY_PUT")
    total = len(directional)
    if total < 2:
        return None
    conflict_ratio = min(call_count, put_count) / total
    option_conflict = option_pressure.dominant_direction in {"BUY_CALL", "BUY_PUT"} and any(
        candidate.direction != option_pressure.dominant_direction for candidate in directional
    )
    if total < 3 and call_count > 0 and put_count > 0:
        return None
    if conflict_ratio < CONFLICTING_SIGNAL_THRESHOLD and not option_conflict:
        return None
    return NoTradeSignal(
        reason="NO_TRADE_CONFLICTING_SIGNALS",
        severity=max(conflict_ratio, 0.55 if option_conflict else 0.0),
        message="Candidate directions conflict or disagree with dominant option pressure.",
        blockers=("CONFLICTING_TRAP_SIGNAL",),
        evidence={
            "call_candidate_count": call_count,
            "put_candidate_count": put_count,
            "directional_candidate_count": total,
            "conflict_ratio": conflict_ratio,
            "dominant_option_direction": option_pressure.dominant_direction,
        },
    )


def _candidate_pool_quality_signal(candidates: tuple[StrategyCandidate, ...], regime: MovementRegimeResult) -> NoTradeSignal | None:
    if len(candidates) < 3:
        return None
    rows = []
    for candidate in candidates:
        payload = asdict(candidate)
        blockers = [str(item or "").strip().upper() for item in payload.get("blockers") or [] if str(item or "").strip()]
        payload["fallback_used"] = any("FALLBACK" in blocker for blocker in blockers)
        payload["candidate_type"] = payload.get("candidate_type") or payload.get("movement_type")
        payload["candidate_origin"] = payload.get("candidate_origin") or ",".join(payload.get("source_signals") or [])
        payload["row_kind"] = "fallback" if payload["fallback_used"] else "primary"
        payload["permission"] = "BLOCK" if payload["fallback_used"] or str(payload.get("status") or "").upper().startswith("BLOCKED") else "EXECUTE"
        payload["final_action"] = payload["permission"]
        payload["reportable_executable"] = not payload["fallback_used"]
        payload["execution_allowed"] = not payload["fallback_used"]
        payload["execution_truth_state"] = "RECOVERY_BLOCKED" if payload["fallback_used"] else "EXEMPLAR"
        rows.append(payload)

    report = analyze_candidate_pool(rows)
    penalty, coverage_reasons = _pool_regime_coverage_penalty(report, regime)
    if report.readiness_state not in {"FALLBACK_HEAVY", "CONCENTRATED", "ONE_SIDED"} and penalty <= 0.0:
        return None
    if report.quality_score >= 0.5 and report.fallback_contamination_ratio < 0.34 and penalty <= 0.0:
        return None

    reason = "NO_TRADE_POOL_CONCENTRATION"
    blockers = []
    if report.fallback_count > 0:
        blockers.append("FALLBACK_CONTAMINATION")
    if report.duplicate_candidate_count > 0:
        blockers.append("DUPLICATE_CANDIDATES")
    if report.same_symbol_concentration_count > 1:
        blockers.append("SAME_SYMBOL_CONCENTRATION")
    if report.same_family_concentration_count > 1:
        blockers.append("SAME_FAMILY_CONCENTRATION")
    if report.bearish_count == 0 or report.bullish_count == 0:
        blockers.append("ONE_SIDED_DIRECTION_COVERAGE")
    blockers.extend(coverage_reasons)

    return NoTradeSignal(
        reason=reason,
        severity=max(0.55, 1.0 - report.quality_score, penalty),
        message="Candidate pool is too concentrated or contaminated to trust as trade-ready.",
        blockers=tuple(blockers) if blockers else ("POOL_CONCENTRATION",),
        warnings=tuple(report.reasons),
        evidence={
            "candidate_count": report.candidate_count,
            "quality_score": report.quality_score,
            "readiness_state": report.readiness_state,
            "fallback_count": report.fallback_count,
            "fallback_contamination_ratio": report.fallback_contamination_ratio,
            "duplicate_candidate_count": report.duplicate_candidate_count,
            "unique_symbol_count": report.unique_symbol_count,
            "unique_strategy_family_count": report.unique_strategy_family_count,
            "bullish_count": report.bullish_count,
            "bearish_count": report.bearish_count,
            "range_count": report.range_count,
            "regime": str(getattr(regime, "primary_regime", "") or "").strip().upper(),
            "coverage_penalty": penalty,
        },
    )


def _pool_regime_coverage_penalty(report: Any, regime: MovementRegimeResult) -> tuple[float, list[str]]:
    penalty = 0.0
    reasons: list[str] = []
    regime_name = str(getattr(regime, "primary_regime", "") or "").strip().upper()
    directional_count = int(report.bullish_count + report.bearish_count)
    directional_ratio = clamp_score(directional_count / max(1, report.candidate_count))

    if regime_name in {"BEARISH", "TREND_DOWN"} and report.bearish_count == 0:
        penalty += 0.20
        reasons.append("NO_BEARISH_COVERAGE")
    if regime_name in {"RANGE", "SIDEWAYS"} and report.range_count == 0:
        penalty += 0.20
        reasons.append("NO_RANGE_COVERAGE")
    if regime_name in {"CHOP", "NOISE", "UNCLEAR"}:
        if report.candidate_count < 3:
            penalty += 0.12
            reasons.append("CHOP_THIN_POOL")
        if directional_ratio > 0.65:
            penalty += 0.14
            reasons.append("CHOP_DIRECTIONAL_HEAVY")
        if report.range_count == 0 and report.advisory_count == 0:
            penalty += 0.08
            reasons.append("CHOP_NO_RANGE_OR_ADVISORY")
        if report.quality_score <= 0.35:
            penalty += 0.10
            reasons.append("CHOP_LOW_QUALITY")
    return _clamp_score(penalty), reasons


def _candidate_baseline_signal(candidates: tuple[StrategyCandidate, ...]) -> NoTradeSignal | None:
    if not candidates:
        return None
    verdicts: list[str] = []
    reasons: list[str] = []
    for candidate in candidates:
        evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
        verdict = str(evidence.get("baseline_verdict") or evidence.get("expectancy_baseline_verdict") or "").strip().upper()
        if verdict:
            verdicts.append(verdict)
        reason = str(evidence.get("baseline_reason") or evidence.get("expectancy_baseline_reason") or "").strip()
        if reason:
            reasons.append(reason)
    if not verdicts:
        return None
    if any(verdict == "OUTPERFORMS" for verdict in verdicts):
        return None
    if any(verdict == "MATCHES" for verdict in verdicts):
        return None
    if not all(verdict in {"UNDERPERFORMS", "INSUFFICIENT_SAMPLE"} for verdict in verdicts):
        return None

    return NoTradeSignal(
        reason="NO_TRADE_BASELINE_WEAKNESS",
        severity=0.58,
        message="All available candidates are at or below the baseline and the pool should stay advisory.",
        blockers=("BASELINE_WEAKNESS",),
        warnings=tuple(sorted(set(reasons))) if reasons else ("baseline_weakness",),
        evidence={
            "candidate_count": len(candidates),
            "baseline_verdicts": sorted(set(verdicts)),
            "underperform_count": sum(1 for verdict in verdicts if verdict == "UNDERPERFORMS"),
            "insufficient_count": sum(1 for verdict in verdicts if verdict == "INSUFFICIENT_SAMPLE"),
        },
    )


def _clamp_score(value: float) -> float:
    return clamp_score(value)


def check_no_trade_conditions() -> dict[str, Any]:
    """Legacy compatibility wrapper.

    Returns the original ``allowed``/``reason`` shape. New opportunity-engine code
    should use ``assess_no_trade`` with injected context.
    """

    now = now_ist().time()
    if now < time(10, 15):
        return {"allowed": False, "reason": "Market too early (<10:15 AM)"}
    if time(11, 30) <= now <= time(13, 30):
        return {"allowed": False, "reason": "Midday chop window (11:30–1:30)"}

    nifty_ltp = get_nifty_ltp()
    vwap = get_index_vwap("NIFTY")
    if not nifty_ltp or not vwap:
        return {"allowed": False, "reason": "Market data unavailable"}

    vwap_distance = abs(nifty_ltp - vwap) / nifty_ltp * 100
    if vwap_distance < 0.15:
        return {"allowed": False, "reason": "Price hugging VWAP (no momentum)"}
    return {"allowed": True, "reason": "Trade allowed"}


def get_nifty_ltp() -> float | None:
    """Legacy helper shim kept monkeypatchable and import-safe."""

    try:
        from core import market_data
    except Exception:
        return None
    helper = getattr(market_data, "get_nifty_ltp", None)
    if not callable(helper):
        return None
    try:
        return safe_float(helper())
    except Exception:
        return None


def get_index_vwap(symbol: str) -> float | None:
    """Legacy helper shim kept monkeypatchable and import-safe."""

    try:
        from core import market_data
    except Exception:
        return None
    helper = getattr(market_data, "get_index_vwap", None)
    if callable(helper):
        try:
            return safe_float(helper(symbol))
        except Exception:
            return None
    helper = getattr(market_data, "get_vwap", None)
    if callable(helper):
        try:
            return safe_float(helper(symbol))
        except Exception:
            return None
    return None


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def clamp_score(value: float | None, low: float = 0.0, high: float = 1.0) -> float:
    if value is None or not math.isfinite(float(value)):
        return low
    return max(low, min(high, float(value)))


__all__ = [
    "CHOP_THRESHOLD",
    "CONFLICTING_SIGNAL_THRESHOLD",
    "INCONCLUSIVE_THRESHOLD",
    "MAX_OPTION_LTP_AGE_SEC",
    "MAX_OPTION_SPREAD_PCT",
    "MIN_DOMINANT_OPTION_SCORE",
    "MIN_OPTION_DEPTH",
    "NoTradeAssessment",
    "NoTradeReason",
    "NoTradeSignal",
    "assess_no_trade",
    "check_no_trade_conditions",
    "get_index_vwap",
    "get_nifty_ltp",
]
