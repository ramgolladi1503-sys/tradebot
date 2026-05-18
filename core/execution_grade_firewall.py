"""Read-only execution-grade candidate firewall.

This module does not place orders, mutate ranking reports, or call brokers. It
centralizes the final pre-selection safety checks that decide whether a movement
candidate has execution-grade evidence or must remain advisory/blocked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.movement_contract import HARD_EXECUTION_BLOCKERS, StrategyCandidate, StrategyContext, has_hard_blocker
from core.option_token_resolver import is_safe_nearest_contract_fallback

EXECUTION_GRADE_SCHEMA_VERSION = 1
DEFAULT_MAX_OPTION_LTP_AGE_SEC = 2.5
DEFAULT_MAX_SPREAD_PCT = 3.0
DEFAULT_MIN_DEPTH = 1.0

TRUSTED_QUOTE_SOURCES: frozenset[str] = frozenset(
    {
        "live_option_tick",
        "live_option_depth",
        "kite_ws",
        "kite_depth_ws",
        "broker_live_quote",
    }
)


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _norm_lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if out == out else None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _mapping_get(mapping: Mapping[str, Any] | None, key: str, default: Any = None) -> Any:
    if not isinstance(mapping, Mapping):
        return default
    return mapping.get(key, default)


def _selected_leg(candidate: StrategyCandidate) -> str | None:
    if candidate.direction == "BUY_CALL":
        return "ce"
    if candidate.direction == "BUY_PUT":
        return "pe"
    return None


def _candidate_blockers(candidate: StrategyCandidate) -> tuple[str, ...]:
    return tuple(_norm(item) for item in (candidate.blockers or ()) if str(item).strip())


def _contract_resolution_blockers(contract_resolution: Mapping[str, Any] | None) -> tuple[str, ...]:
    if contract_resolution is None:
        return ("UNRESOLVED_CONTRACT",)
    if is_safe_nearest_contract_fallback(dict(contract_resolution)):
        return ("FALLBACK_QUOTE_ONLY",)
    if _bool(_mapping_get(contract_resolution, "fallback_candidate")):
        return ("FALLBACK_QUOTE_ONLY",)
    if _bool(_mapping_get(contract_resolution, "advisory_only")):
        return ("FALLBACK_QUOTE_ONLY",)
    if _mapping_get(contract_resolution, "instrument_token") in (None, "", "None"):
        return ("UNRESOLVED_CONTRACT",)
    if _mapping_get(contract_resolution, "execution_grade") is False:
        return ("UNRESOLVED_CONTRACT",)
    return ()


def _context_blockers(
    candidate: StrategyCandidate,
    context: StrategyContext | None,
    *,
    max_option_ltp_age_sec: float,
    max_spread_pct: float,
    min_depth: float,
) -> tuple[str, ...]:
    if context is None:
        return ()

    blockers: list[str] = []
    if bool(context.fallback_used):
        blockers.append("FALLBACK_QUOTE_ONLY")

    quote_source = _norm_lower(context.quote_source)
    if quote_source and quote_source not in TRUSTED_QUOTE_SOURCES:
        blockers.append("QUOTE_SOURCE_UNTRUSTED")

    age = _as_float(context.option_ltp_age_sec)
    if age is None:
        blockers.append("STALE_OPTION_LTP")
    elif age > max_option_ltp_age_sec:
        blockers.append("STALE_OPTION_LTP")

    leg = _selected_leg(candidate)
    if leg is None:
        blockers.append("UNRESOLVED_CONTRACT")
        return tuple(blockers)

    ltp = _as_float(getattr(context, f"option_{leg}_ltp", None))
    spread = _as_float(getattr(context, f"{leg}_spread_pct", None))
    depth = _as_float(getattr(context, f"{leg}_depth", None))

    if ltp is None or ltp <= 0.0:
        blockers.append("STALE_OPTION_LTP")
    if spread is None or spread > max_spread_pct:
        blockers.append("WIDE_SPREAD")
    if depth is None or depth < min_depth:
        blockers.append("MISSING_DEPTH")

    return tuple(blockers)


@dataclass(frozen=True)
class ExecutionGradeDecision:
    schema_version: int
    strategy_id: str
    symbol: str
    direction: str
    execution_grade: bool
    allowed_for_execution: bool
    allowed_for_paper_execution: bool
    advisory_only: bool
    state: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    is_order_action: bool = False
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        return payload


def assess_execution_grade(
    candidate: StrategyCandidate,
    context: StrategyContext | None = None,
    *,
    contract_resolution: Mapping[str, Any] | None = None,
    max_option_ltp_age_sec: float = DEFAULT_MAX_OPTION_LTP_AGE_SEC,
    max_spread_pct: float = DEFAULT_MAX_SPREAD_PCT,
    min_depth: float = DEFAULT_MIN_DEPTH,
) -> ExecutionGradeDecision:
    """Return a fail-closed execution-grade decision for one candidate.

    The function is deterministic and read-only. Missing resolver evidence is
    considered unresolved and therefore not execution-grade.
    """

    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    candidate_blockers = _candidate_blockers(candidate)
    blockers.extend(candidate_blockers)

    if candidate.status not in {"VALIDATED_CANDIDATE", "RANKED_OPPORTUNITY"}:
        blockers.append("CANDIDATE_NOT_EXECUTION_ELIGIBLE")
    if candidate.direction == "NO_TRADE":
        blockers.append("NO_TRADE_CANDIDATE")
    if has_hard_blocker(candidate.blockers):
        reasons.append("candidate_has_hard_execution_blocker")

    blockers.extend(
        _contract_resolution_blockers(contract_resolution)
    )
    blockers.extend(
        _context_blockers(
            candidate,
            context,
            max_option_ltp_age_sec=max_option_ltp_age_sec,
            max_spread_pct=max_spread_pct,
            min_depth=min_depth,
        )
    )

    normalized_blockers = tuple(sorted({item for item in blockers if item}))
    hard_blocked = bool(set(normalized_blockers).intersection(HARD_EXECUTION_BLOCKERS))
    blocked = bool(normalized_blockers)
    execution_grade = not blocked and not hard_blocked

    if execution_grade:
        state = "EXECUTION_GRADE"
        reasons.append("candidate_has_exact_contract_fresh_quote_spread_and_depth")
    elif "FALLBACK_QUOTE_ONLY" in normalized_blockers or "QUOTE_SOURCE_UNTRUSTED" in normalized_blockers:
        state = "ADVISORY_ONLY"
        reasons.append("fallback_or_untrusted_quote_is_not_execution_grade")
    else:
        state = "BLOCKED"
        reasons.append("candidate_failed_execution_grade_firewall")

    if contract_resolution is not None and is_safe_nearest_contract_fallback(dict(contract_resolution)):
        warnings.append("safe_nearest_contract_fallback_visible_but_advisory_only")

    return ExecutionGradeDecision(
        schema_version=EXECUTION_GRADE_SCHEMA_VERSION,
        strategy_id=candidate.strategy_id,
        symbol=candidate.symbol,
        direction=candidate.direction,
        execution_grade=execution_grade,
        allowed_for_execution=execution_grade,
        allowed_for_paper_execution=execution_grade,
        advisory_only=state == "ADVISORY_ONLY",
        state=state,
        blockers=normalized_blockers,
        warnings=tuple(sorted({item for item in warnings if item})),
        reasons=tuple(sorted({item for item in reasons if item})),
    )


__all__ = [
    "ExecutionGradeDecision",
    "assess_execution_grade",
]
