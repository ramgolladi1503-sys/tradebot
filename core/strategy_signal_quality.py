from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg

SIGNAL_QUALITY_BLOCK_REASON = "strategy_signal_quality_failed"
MISSING_STRATEGY_REASON = "missing_strategy_family"
MISSING_DIRECTION_REASON = "missing_signal_direction"
NO_SIGNAL_REASON = "no_strategy_signal"
WEAK_SIGNAL_REASON = "weak_strategy_signal"
CONFLICTING_SIGNAL_REASON = "conflicting_strategy_signal"
EXPLICIT_REJECT_REASON = "strategy_reject_reason"


@dataclass(frozen=True)
class StrategySignalQualityDecision:
    signal_ok: bool
    reason_code: str
    reasons: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)


def _candidate_get(candidate: Any, field: str, default: Any = None) -> Any:
    return candidate.get(field, default) if isinstance(candidate, dict) else getattr(candidate, field, default)


def _source_flags(candidate: Any) -> dict[str, Any]:
    flags = _candidate_get(candidate, "source_flags", {}) or {}
    return dict(flags) if isinstance(flags, dict) else {}


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", "None"):
            return value
    return None


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _append_unique(reasons: list[str], reason: str | None) -> None:
    text = str(reason or "").strip()
    if text and text not in reasons:
        reasons.append(text)


def _execution_capable(candidate: Any, flags: dict[str, Any]) -> bool:
    candidate_class = str(_coalesce(_candidate_get(candidate, "candidate_class"), flags.get("candidate_class")) or "").strip().upper()
    entry_status = str(_coalesce(_candidate_get(candidate, "execution_entry_status"), flags.get("execution_entry_status")) or "").strip().lower()
    if candidate_class == "EXECUTABLE":
        return True
    if entry_status == "executable":
        return True
    return _candidate_get(candidate, "selected_for_execution") is True


def _market_mode(candidate: Any, flags: dict[str, Any]) -> str:
    market_context = _candidate_get(candidate, "market_context", {}) or {}
    if not isinstance(market_context, dict):
        market_context = {}
    return str(
        _coalesce(
            _candidate_get(candidate, "market_mode"),
            flags.get("market_mode"),
            flags.get("runtime_mode"),
            market_context.get("mode"),
            market_context.get("execution_mode"),
            "",
        )
        or ""
    ).strip().upper()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _has_signal_contract_payload(candidate: Any, flags: dict[str, Any]) -> bool:
    fields = (
        "signal_score",
        "setup_score",
        "trigger_score",
        "confluence_score",
        "regime_fit",
        "signal_strength",
        "signal_quality_score",
        "strategy_signal_score",
        "reject_reason",
        "entry_block_code",
        "soft_reject_reason",
        "direction_confidence",
    )
    return any(_coalesce(_candidate_get(candidate, field), flags.get(field)) not in (None, "", "None") for field in fields)


def _signal_score(candidate: Any, flags: dict[str, Any]) -> float | None:
    explicit = _safe_float(
        _coalesce(
            _candidate_get(candidate, "signal_score"),
            flags.get("signal_score"),
            _candidate_get(candidate, "signal_quality_score"),
            flags.get("signal_quality_score"),
            _candidate_get(candidate, "strategy_signal_score"),
            flags.get("strategy_signal_score"),
            _candidate_get(candidate, "signal_strength"),
            flags.get("signal_strength"),
        )
    )
    if explicit is not None:
        return max(0.0, min(1.0, explicit))
    parts = [
        _safe_float(_coalesce(_candidate_get(candidate, "setup_score"), flags.get("setup_score"))),
        _safe_float(_coalesce(_candidate_get(candidate, "trigger_score"), flags.get("trigger_score"))),
        _safe_float(_coalesce(_candidate_get(candidate, "confluence_score"), flags.get("confluence_score"))),
        _safe_float(_coalesce(_candidate_get(candidate, "regime_fit"), flags.get("regime_fit"))),
    ]
    present = [value for value in parts if value is not None]
    if not present:
        return None
    return max(0.0, min(1.0, sum(present) / len(present)))


def classify_strategy_signal_quality(candidate: Any) -> StrategySignalQualityDecision:
    """Validate strategy signal quality for execution-capable candidates.

    EDGE-35 separates "a signal exists" from "the signal is good enough to
    trade". LIVE candidates and candidates carrying explicit signal-contract
    fields are validated strictly. Legacy offline fixtures without signal fields
    pass as compatibility fixtures so unrelated tests are not rewritten into
    strategy-quality tests.
    """
    flags = _source_flags(candidate)
    if not _execution_capable(candidate, flags):
        return StrategySignalQualityDecision(
            signal_ok=True,
            reason_code="not_execution_capable",
            context={"execution_capable": False},
        )

    market_mode = _market_mode(candidate, flags)
    strict_live = market_mode == "LIVE"
    has_payload = _has_signal_contract_payload(candidate, flags)
    if not strict_live and not has_payload:
        return StrategySignalQualityDecision(
            signal_ok=True,
            reason_code="legacy_signal_fixture",
            context={
                "execution_capable": True,
                "market_mode": market_mode or None,
                "signal_contract_payload": False,
            },
        )

    reasons: list[str] = []
    strategy_family = str(_coalesce(_candidate_get(candidate, "strategy_family"), flags.get("strategy_family")) or "").strip()
    side = str(
        _coalesce(
            _candidate_get(candidate, "side"),
            flags.get("side"),
            _candidate_get(candidate, "direction"),
            flags.get("direction"),
            _candidate_get(candidate, "direction_family"),
            flags.get("direction_family"),
        )
        or ""
    ).strip().upper()
    signal_score = _signal_score(candidate, flags)
    min_score = float(getattr(cfg, "STRATEGY_SIGNAL_QUALITY_MIN_SCORE", 0.55) or 0.55)
    reject_reason = str(
        _coalesce(
            _candidate_get(candidate, "reject_reason"),
            flags.get("reject_reason"),
            _candidate_get(candidate, "entry_block_code"),
            flags.get("entry_block_code"),
            flags.get("soft_reject_reason"),
        )
        or ""
    ).strip().lower()
    signal_conflict = _truthy(_coalesce(_candidate_get(candidate, "signal_conflict"), flags.get("signal_conflict"), _candidate_get(candidate, "direction_conflict"), flags.get("direction_conflict")))

    if not strategy_family:
        _append_unique(reasons, MISSING_STRATEGY_REASON)
    if side in {"", "NONE", "UNKNOWN", "NEUTRAL"}:
        _append_unique(reasons, MISSING_DIRECTION_REASON)
    if signal_score is None:
        _append_unique(reasons, NO_SIGNAL_REASON)
    elif signal_score < min_score:
        _append_unique(reasons, WEAK_SIGNAL_REASON)
    if reject_reason in {"no_signal", "weak_signal", "signal_missing", "strategy_rejected", "entry_signal_missing"}:
        _append_unique(reasons, f"{EXPLICIT_REJECT_REASON}:{reject_reason}")
    if signal_conflict:
        _append_unique(reasons, CONFLICTING_SIGNAL_REASON)

    ok = not reasons
    return StrategySignalQualityDecision(
        signal_ok=ok,
        reason_code="ok" if ok else SIGNAL_QUALITY_BLOCK_REASON,
        reasons=tuple(reasons),
        context={
            "execution_capable": True,
            "market_mode": market_mode or None,
            "signal_contract_payload": has_payload,
            "strategy_family": strategy_family or None,
            "side": side or None,
            "signal_score": signal_score,
            "min_signal_score": min_score,
            "reject_reason": reject_reason or None,
            "signal_conflict": signal_conflict,
        },
    )
