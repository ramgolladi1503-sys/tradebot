from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import config as cfg

SPREAD_TRUTH_BLOCK_REASON = "option_spread_truth_failed"
MISSING_BID_REASON = "missing_option_bid"
MISSING_ASK_REASON = "missing_option_ask"
INVALID_BID_ASK_REASON = "invalid_option_bid_ask"
WIDE_SPREAD_REASON = "wide_option_spread"
LTP_OUTSIDE_SPREAD_REASON = "ltp_outside_bid_ask"
FALLBACK_SPREAD_REASON = "fallback_spread_source"
PARTIAL_QUOTE_REASON = "partial_quote"


@dataclass(frozen=True)
class OptionSpreadTruthDecision:
    spread_ok: bool
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


def _max_spread_pct() -> float:
    return float(getattr(cfg, "OPTION_SPREAD_TRUTH_MAX_SPREAD_PCT", getattr(cfg, "MAX_OPTION_SPREAD_PCT", 0.05)) or 0.05)


def _max_ltp_drift_pct() -> float:
    return float(getattr(cfg, "OPTION_SPREAD_TRUTH_MAX_LTP_DRIFT_PCT", 0.02) or 0.02)


def classify_option_spread_truth(candidate: Any) -> OptionSpreadTruthDecision:
    """Validate bid/ask/spread truth for execution-capable option candidates.

    EDGE-33 makes LTP-only rows non-executable. A candidate must carry usable
    bid/ask, an acceptable spread, and no fallback spread source before it can
    pass the executable truth firebreak.
    """
    flags = _source_flags(candidate)
    if not _execution_capable(candidate, flags):
        return OptionSpreadTruthDecision(
            spread_ok=True,
            reason_code="not_execution_capable",
            context={"execution_capable": False},
        )

    reasons: list[str] = []
    bid = _safe_float(_coalesce(_candidate_get(candidate, "best_bid"), flags.get("best_bid"), _candidate_get(candidate, "opt_bid"), flags.get("opt_bid"), _candidate_get(candidate, "bid"), flags.get("bid")))
    ask = _safe_float(_coalesce(_candidate_get(candidate, "best_ask"), flags.get("best_ask"), _candidate_get(candidate, "opt_ask"), flags.get("opt_ask"), _candidate_get(candidate, "ask"), flags.get("ask")))
    ltp = _safe_float(_coalesce(_candidate_get(candidate, "ltp"), flags.get("ltp"), _candidate_get(candidate, "option_ltp"), flags.get("option_ltp"), _candidate_get(candidate, "execution_entry"), flags.get("execution_entry")))
    spread_pct = _safe_float(_coalesce(_candidate_get(candidate, "spread_pct"), flags.get("spread_pct")))
    spread_source = str(_coalesce(_candidate_get(candidate, "spread_source"), flags.get("spread_source"), _candidate_get(candidate, "quote_source"), flags.get("quote_source")) or "").strip().lower()
    quote_completeness = str(_coalesce(_candidate_get(candidate, "quote_completeness"), flags.get("quote_completeness"), "FULL") or "FULL").strip().upper()

    if bid is None or bid <= 0:
        _append_unique(reasons, MISSING_BID_REASON)
    if ask is None or ask <= 0:
        _append_unique(reasons, MISSING_ASK_REASON)
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        if ask < bid:
            _append_unique(reasons, INVALID_BID_ASK_REASON)
        else:
            mid = (bid + ask) / 2.0
            calculated_spread_pct = (ask - bid) / max(mid, 1e-9)
            spread_pct = calculated_spread_pct if spread_pct is None else spread_pct
            if calculated_spread_pct > _max_spread_pct():
                _append_unique(reasons, WIDE_SPREAD_REASON)
            if ltp is not None:
                low = bid * (1.0 - _max_ltp_drift_pct())
                high = ask * (1.0 + _max_ltp_drift_pct())
                if ltp < low or ltp > high:
                    _append_unique(reasons, LTP_OUTSIDE_SPREAD_REASON)

    if quote_completeness not in {"FULL", "COMPLETE"}:
        _append_unique(reasons, PARTIAL_QUOTE_REASON)
    if spread_source in {"fallback", "synthetic", "derived_fallback", "close_fallback", "quote_fallback"}:
        _append_unique(reasons, FALLBACK_SPREAD_REASON)

    ok = not reasons
    return OptionSpreadTruthDecision(
        spread_ok=ok,
        reason_code="ok" if ok else SPREAD_TRUTH_BLOCK_REASON,
        reasons=tuple(reasons),
        context={
            "execution_capable": True,
            "bid": bid,
            "ask": ask,
            "ltp": ltp,
            "spread_pct": spread_pct,
            "max_spread_pct": _max_spread_pct(),
            "max_ltp_drift_pct": _max_ltp_drift_pct(),
            "spread_source": spread_source or None,
            "quote_completeness": quote_completeness,
        },
    )
