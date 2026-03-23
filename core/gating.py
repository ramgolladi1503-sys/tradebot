"""Deterministic hard/soft gating contract for execution readiness."""

from __future__ import annotations

from typing import Any

from config import config as cfg


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _first_float(mapping: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in mapping:
            continue
        value = _as_float(mapping.get(key))
        if value is not None:
            return value
    return None


def _clamp(value: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, value))


def _coerce_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, "", "None"):
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def _context_value(candidate: dict[str, Any], snapshot: dict[str, Any], *keys: str) -> Any:
    for mapping in (candidate, snapshot):
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            if key in mapping and mapping.get(key) not in (None, "", "None"):
                return mapping.get(key)
    return None


def _context_mode(candidate: dict[str, Any], snapshot: dict[str, Any]) -> str:
    return str(_context_value(candidate, snapshot, "execution_mode", "mode") or "").strip().upper()


def _context_market_open(candidate: dict[str, Any], snapshot: dict[str, Any]) -> bool | None:
    return _coerce_optional_bool(_context_value(candidate, snapshot, "market_open"))


def _context_allow_stale_quotes(candidate: dict[str, Any], snapshot: dict[str, Any]) -> bool | None:
    return _coerce_optional_bool(_context_value(candidate, snapshot, "allow_stale_quotes"))


def _should_relax_non_live_hard_gates(candidate: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    if not bool(getattr(cfg, "GATING_RELAX_NON_LIVE_HARD_GATES", True)):
        return False
    mode = _context_mode(candidate, snapshot)
    market_open = _context_market_open(candidate, snapshot)
    allow_stale_quotes = _context_allow_stale_quotes(candidate, snapshot)
    relaxed_mode = mode in {"SIM", "PAPER", "OFFHOURS", "ADVISORY", "PLANNING"}
    return bool(relaxed_mode or market_open is False or allow_stale_quotes is True)


def _relax_non_live_hard_reasons(hard_reasons: list[str]) -> tuple[list[str], list[str], list[str]]:
    soft_codes = {
        str(code).strip().upper()
        for code in getattr(cfg, "GATING_RELAX_NON_LIVE_SOFT_CODES", ("HARD_STALE_LTP", "HARD_MISSING_VOLUME"))
        if str(code).strip()
    }
    warning_codes = {
        str(code).strip().upper()
        for code in getattr(cfg, "GATING_RELAX_NON_LIVE_WARNING_CODES", ("HARD_NO_LTP", "HARD_MISSING_TICK_AGE"))
        if str(code).strip()
    }
    remaining: list[str] = []
    relaxed_soft: list[str] = []
    relaxed_warning: list[str] = []
    for reason in list(hard_reasons or []):
        normalized = str(reason or "").strip().upper()
        if not normalized:
            continue
        if normalized in soft_codes:
            relaxed_soft.append(normalized)
        elif normalized in warning_codes:
            relaxed_warning.append(normalized)
        else:
            remaining.append(normalized)
    return remaining, relaxed_soft, relaxed_warning


def _age_and_threshold(candidate: dict[str, Any], snapshot: dict[str, Any]) -> tuple[float | None, float]:
    freshness = snapshot.get("freshness") if isinstance(snapshot.get("freshness"), dict) else {}
    age = _first_float(candidate, ("option_age_sec", "price_age_sec", "quote_age_sec", "ltp_age_sec"))
    if age is None:
        age = _as_float(freshness.get("max_tick_age_sec"))
    threshold = _as_float(freshness.get("sla_threshold_sec"))
    if threshold is None or threshold <= 0:
        threshold = _as_float(getattr(cfg, "GATING_HARD_MAX_TICK_AGE_SEC", None))
    if threshold is None or threshold <= 0:
        threshold = float(getattr(cfg, "OPTION_LTP_SLA_SEC", 2.0))
    return age, float(threshold)


def _has_valid_quote_liquidity_surrogate(candidate: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    ltp = _first_float(candidate, ("current_ltp", "live_ltp", "ltp", "entry"))
    if ltp is None or ltp <= 0:
        return False
    age, age_threshold = _age_and_threshold(candidate, snapshot)
    if age is None or age > age_threshold:
        return False
    bid = _first_float(candidate, ("best_bid", "bid", "opt_bid"))
    ask = _first_float(candidate, ("best_ask", "ask", "opt_ask"))
    if bid is None or ask is None:
        return False
    return bool(bid > 0 and ask > 0 and ask >= bid)


def apply_hard_gates(candidate: dict[str, Any], snapshot: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Structural gates that can block execution directly.
    """
    reasons: list[str] = []

    ltp = _first_float(candidate, ("current_ltp", "live_ltp", "ltp", "entry"))
    if ltp is None or ltp <= 0:
        reasons.append("HARD_NO_LTP")

    age, age_threshold = _age_and_threshold(candidate, snapshot)
    if age is None:
        reasons.append("HARD_MISSING_TICK_AGE")
    elif age > age_threshold:
        reasons.append("HARD_STALE_LTP")

    spread_pct = _first_float(candidate, ("spread_pct",))
    max_spread = _as_float(
        getattr(
            cfg,
            "GATING_HARD_MAX_SPREAD_PCT",
            getattr(cfg, "MAX_SPREAD_PCT", 0.03),
        )
    )
    if spread_pct is not None and max_spread is not None and max_spread > 0 and spread_pct > max_spread:
        reasons.append("HARD_SPREAD_TOO_WIDE")

    volume = _first_float(candidate, ("volume", "current_volume", "tick_volume"))
    min_volume = _as_float(
        getattr(
            cfg,
            "GATING_HARD_MIN_VOLUME",
            getattr(cfg, "MIN_VOLUME_FILTER", 1),
        )
    )
    if min_volume is None:
        min_volume = 1.0
    allow_missing_volume_on_valid_quotes = bool(
        getattr(cfg, "GATING_ALLOW_MISSING_VOLUME_WITH_VALID_QUOTES", True)
    )
    volume_missing_but_quotes_usable = bool(
        volume is None
        and allow_missing_volume_on_valid_quotes
        and _has_valid_quote_liquidity_surrogate(candidate, snapshot)
    )
    if (volume is None and not volume_missing_but_quotes_usable) or (volume is not None and volume < min_volume):
        reasons.append("HARD_MISSING_VOLUME")

    return len(reasons) == 0, reasons


def apply_soft_gates(candidate: dict[str, Any], snapshot: dict[str, Any]) -> tuple[float, list[str]]:
    """
    Soft gates adjust confidence only. They never directly block.
    Returns a negative/positive score delta and reasons.
    """
    reasons: list[str] = []
    delta = 0.0

    feed_state = str(
        candidate.get("feed_state")
        or snapshot.get("feed_state")
        or ""
    ).upper()
    if feed_state in {"DEGRADED", "DOWN", "UNKNOWN"}:
        penalty = float(getattr(cfg, "GATING_SOFT_PENALTY_FEED_STATE", 0.05))
        delta -= penalty
        reasons.append(f"SOFT_FEED_{feed_state}")

    age, age_threshold = _age_and_threshold(candidate, snapshot)
    if age is not None and age_threshold > 0:
        ratio = age / age_threshold
        if ratio > 0.5:
            max_penalty = float(getattr(cfg, "GATING_SOFT_PENALTY_MAX_AGE", 0.12))
            penalty = min(max_penalty, (ratio - 0.5) * 2.0 * max_penalty)
            if penalty > 0:
                delta -= penalty
                reasons.append("SOFT_AGE_NEAR_LIMIT")

    spread_pct = _first_float(candidate, ("spread_pct",))
    max_spread = _as_float(
        getattr(
            cfg,
            "GATING_HARD_MAX_SPREAD_PCT",
            getattr(cfg, "MAX_SPREAD_PCT", 0.03),
        )
    )
    if spread_pct is not None and max_spread is not None and max_spread > 0:
        spread_ratio = spread_pct / max_spread
        if spread_ratio > 0.7:
            max_penalty = float(getattr(cfg, "GATING_SOFT_PENALTY_MAX_SPREAD", 0.10))
            penalty = min(max_penalty, (spread_ratio - 0.7) / 0.3 * max_penalty)
            if penalty > 0:
                delta -= penalty
                reasons.append("SOFT_SPREAD_ELEVATED")

    volume = _first_float(candidate, ("volume", "current_volume", "tick_volume"))
    min_volume = _as_float(
        getattr(
            cfg,
            "GATING_HARD_MIN_VOLUME",
            getattr(cfg, "MIN_VOLUME_FILTER", 1),
        )
    )
    allow_missing_volume_on_valid_quotes = bool(
        getattr(cfg, "GATING_ALLOW_MISSING_VOLUME_WITH_VALID_QUOTES", True)
    )
    if (
        volume is None
        and allow_missing_volume_on_valid_quotes
        and _has_valid_quote_liquidity_surrogate(candidate, snapshot)
    ):
        penalty = float(getattr(cfg, "GATING_SOFT_PENALTY_MISSING_VOLUME_WITH_VALID_QUOTES", 0.08))
        if penalty > 0:
            delta -= penalty
            reasons.append("SOFT_MISSING_VOLUME_WITH_VALID_QUOTES")
    elif volume is not None and min_volume is not None and min_volume > 0 and volume < min_volume:
        max_penalty = float(getattr(cfg, "GATING_SOFT_PENALTY_LOW_VOLUME", 0.06))
        ratio = max(0.0, 1.0 - (volume / min_volume))
        penalty = min(max_penalty, ratio * max_penalty)
        if penalty > 0:
            delta -= penalty
            reasons.append("SOFT_LOW_VOLUME")

    return float(delta), reasons


def gate_decision(candidate: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    strict_hard_pass, strict_hard_reasons = apply_hard_gates(candidate, snapshot)
    soft_delta, soft_reasons = apply_soft_gates(candidate, snapshot)
    hard_reasons = list(strict_hard_reasons or [])
    relaxed_hard_reasons: list[str] = []
    relaxed_soft_reasons: list[str] = []
    relaxed_warning_reasons: list[str] = []
    relaxed_soft_penalty_total = 0.0
    relaxed_context = _should_relax_non_live_hard_gates(candidate, snapshot)
    if relaxed_context and hard_reasons:
        hard_reasons, relaxed_soft_reasons, relaxed_warning_reasons = _relax_non_live_hard_reasons(hard_reasons)
        relaxed_hard_reasons = [*relaxed_soft_reasons, *relaxed_warning_reasons]
        if relaxed_soft_reasons:
            penalty_per_reason = float(getattr(cfg, "GATING_RELAX_NON_LIVE_SOFT_PENALTY", 0.05))
            relaxed_soft_penalty_total = max(0.0, penalty_per_reason) * float(len(relaxed_soft_reasons))
            soft_delta -= relaxed_soft_penalty_total
            soft_reasons = [*soft_reasons, *relaxed_soft_reasons]
    hard_pass = len(hard_reasons) == 0
    base_conf = _first_float(candidate, ("global_confidence", "confidence", "raw_signal_confidence"))
    if base_conf is None:
        base_conf = float(getattr(cfg, "GATING_DEFAULT_CONFIDENCE", 0.0))
    final_conf = _clamp(float(base_conf) + float(soft_delta), 0.0, 1.0)
    return {
        "hard_pass": bool(hard_pass),
        "strict_hard_pass": bool(strict_hard_pass),
        "soft_score_adjustment": float(soft_delta),
        "base_confidence": float(base_conf),
        "final_confidence": float(final_conf),
        "reasons": [*hard_reasons, *soft_reasons, *relaxed_warning_reasons],
        "hard_reasons": hard_reasons,
        "soft_reasons": soft_reasons,
        "strict_hard_reasons": list(strict_hard_reasons or []),
        "relaxed_context": bool(relaxed_context),
        "relaxed_hard_reasons": relaxed_hard_reasons,
        "relaxed_soft_reasons": relaxed_soft_reasons,
        "relaxed_warning_reasons": relaxed_warning_reasons,
        "relaxed_soft_penalty_total": float(relaxed_soft_penalty_total),
    }
