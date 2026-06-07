from __future__ import annotations

from typing import Any
from math import log1p

from core.quote_truth import quote_consistency_score as canonical_quote_consistency_score

try:
    from config import config as cfg
except Exception:  # pragma: no cover - defensive import fallback
    cfg = None


def _cfg_float(name: str, default: float) -> float:
    try:
        value = getattr(cfg, name, default)
        if value in (None, "", "None"):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _cfg_bool(name: str, default: bool) -> bool:
    try:
        value = getattr(cfg, name, default)
    except Exception:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _clamp01(value: float | None, *, default: float = 0.0) -> float:
    if value is None:
        return float(default)
    return max(0.0, min(1.0, float(value)))


def _round_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _normalize_unit(value: Any) -> float | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    if numeric > 1.0:
        if numeric <= 100.0:
            numeric /= 100.0
        else:
            numeric = 1.0
    return _clamp01(numeric)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _dedupe_texts(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _weighted_average(parts: list[tuple[float | None, float]], *, default: float = 0.0) -> float:
    total_weight = 0.0
    total_score = 0.0
    for value, weight in parts:
        if value is None or weight <= 0.0:
            continue
        total_score += float(value) * float(weight)
        total_weight += float(weight)
    if total_weight <= 0.0:
        return _clamp01(default, default=default)
    return _clamp01(total_score / total_weight, default=default)


def _first_float(*values: Any) -> float | None:
    for value in values:
        numeric = _safe_float(value)
        if numeric is not None:
            return numeric
    return None


def _setup_strength(candidate: dict[str, Any], score_inputs_used: dict[str, Any]) -> float:
    detail = _as_dict(candidate.get("trade_score_detail"))
    source_flags = _as_dict(candidate.get("source_flags"))
    signal_components: list[float] = []

    for field in (
        "trade_score",
        "trade_alignment",
        "builder_confidence",
        "confidence",
        "global_confidence",
        "raw_signal_confidence",
        "rank_score",
    ):
        raw = candidate.get(field)
        score = _normalize_unit(raw)
        if score is not None:
            signal_components.append(score)
            score_inputs_used[field] = raw

    detail_confluence = _normalize_unit(detail.get("confluence_score"))
    if detail_confluence is not None:
        signal_components.append(detail_confluence)
        score_inputs_used["trade_score_detail.confluence_score"] = detail.get("confluence_score")

    strategy_priority = _normalize_unit(
        candidate.get("strategy_priority") or source_flags.get("strategy_priority")
    )
    if strategy_priority is not None:
        signal_components.append(strategy_priority)
        score_inputs_used["strategy_priority"] = candidate.get("strategy_priority") or source_flags.get("strategy_priority")

    regime_alignment_score = _normalize_unit(
        candidate.get("regime_alignment_score") or source_flags.get("regime_alignment_score")
    )
    if regime_alignment_score is not None:
        signal_components.append(regime_alignment_score)
        score_inputs_used["regime_alignment_score"] = candidate.get("regime_alignment_score") or source_flags.get("regime_alignment_score")

    family_consensus_score = _normalize_unit(
        candidate.get("family_consensus_score") or source_flags.get("family_consensus_score")
    )
    if family_consensus_score is not None:
        signal_components.append(family_consensus_score)
        score_inputs_used["family_consensus_score"] = candidate.get("family_consensus_score") or source_flags.get("family_consensus_score")

    base = sum(signal_components) / len(signal_components) if signal_components else 0.56
    pattern_flags = _as_list(candidate.get("pattern_flags") or source_flags.get("pattern_flags"))
    pattern_bonus = min(0.12, 0.03 * len([flag for flag in pattern_flags if str(flag or "").strip()]))
    if pattern_flags:
        score_inputs_used["pattern_flags"] = [str(flag) for flag in pattern_flags]
    if candidate.get("entry_condition") not in (None, "", "None"):
        score_inputs_used["entry_condition"] = candidate.get("entry_condition")
        base += 0.03
    return _clamp01((base * 0.9) + pattern_bonus, default=0.56)


def _regime_fit(candidate: dict[str, Any], market_data: dict[str, Any], score_inputs_used: dict[str, Any]) -> float:
    regime = str(
        market_data.get("regime")
        or candidate.get("regime")
        or market_data.get("day_type")
        or candidate.get("day_type")
        or ""
    ).strip().upper()
    market_open = bool(market_data.get("market_open", candidate.get("market_open", True)))
    countertrend = bool(candidate.get("countertrend"))
    score_inputs_used["regime"] = regime or "UNKNOWN"
    score_inputs_used["market_open"] = market_open
    if countertrend:
        score_inputs_used["countertrend"] = True

    if regime in {"TREND", "UPTREND", "DOWNTREND"}:
        fit = 0.82
    elif regime in {"RANGE", "RANGE_VOLATILE"}:
        fit = 0.64
    elif regime in {"EXPIRY", "EXPIRY_DAY"}:
        fit = 0.48
    elif regime in {"EVENT", "EVENT_DAY", "PANIC", "PANIC_DAY"}:
        fit = 0.34
    else:
        fit = 0.56

    if countertrend:
        fit -= 0.22
    if not market_open:
        fit = min(fit, 0.62)
    explicit_alignment = _normalize_unit(candidate.get("regime_alignment_score"))
    if explicit_alignment is not None:
        score_inputs_used["regime_alignment_score"] = candidate.get("regime_alignment_score")
        fit = _weighted_average([(fit, 0.58), (explicit_alignment, 0.42)], default=fit)
    return _clamp01(fit, default=0.56)


def _liquidity_score(candidate: dict[str, Any], market_data: dict[str, Any], score_inputs_used: dict[str, Any]) -> tuple[float, list[str]]:
    volume = max(
        _first_float(candidate.get("volume"), market_data.get("volume")) or 0.0,
        _first_float(candidate.get("current_volume"), market_data.get("current_volume")) or 0.0,
        _first_float(candidate.get("tick_volume"), market_data.get("tick_volume")) or 0.0,
    )
    oi = max(
        _first_float(candidate.get("oi"), market_data.get("oi")) or 0.0,
        _first_float(candidate.get("oi_change"), market_data.get("oi_change")) or 0.0,
    )
    quote_ok = candidate.get("quote_ok")
    target_volume = max(_cfg_float("CANDIDATE_SCORING_LIQUIDITY_TARGET_VOLUME", 25000.0), 1.0)
    target_oi = max(_cfg_float("CANDIDATE_SCORING_LIQUIDITY_TARGET_OI", 50000.0), 1.0)
    volume_cap_mult = max(_cfg_float("CANDIDATE_SCORING_LIQUIDITY_VOLUME_CAP_MULT", 40.0), 1.0)
    oi_cap_mult = max(_cfg_float("CANDIDATE_SCORING_LIQUIDITY_OI_CAP_MULT", 40.0), 1.0)
    flow_weight = max(0.0, _cfg_float("CANDIDATE_SCORING_LIQUIDITY_FLOW_WEIGHT", 0.60))
    book_weight = max(0.0, _cfg_float("CANDIDATE_SCORING_LIQUIDITY_BOOK_WEIGHT", 0.40))
    reasons: list[str] = []

    if volume <= 0.0 and oi <= 0.0:
        score_inputs_used["liquidity"] = "missing"
        reasons.append("missing_liquidity_context")
        return 0.5, reasons

    volume_score = (
        min(1.0, log1p(max(volume, 0.0)) / log1p(target_volume * volume_cap_mult))
        if volume > 0.0
        else 0.45
    )
    oi_score = (
        min(1.0, log1p(max(oi, 0.0)) / log1p(target_oi * oi_cap_mult))
        if oi > 0.0
        else 0.5
    )
    flow_score = _weighted_average([(volume_score, 0.7), (oi_score, 0.3)], default=0.5)
    quote_consistency = _first_float(
        candidate.get("quote_consistency_score"),
        market_data.get("quote_consistency_score"),
    )
    if quote_consistency is None:
        quote_consistency = canonical_quote_consistency_score(
            current_ltp=_first_float(candidate.get("current_ltp"), market_data.get("current_ltp")),
            best_bid=_first_float(candidate.get("best_bid"), candidate.get("bid"), candidate.get("opt_bid"), market_data.get("best_bid")),
            best_ask=_first_float(candidate.get("best_ask"), candidate.get("ask"), candidate.get("opt_ask"), market_data.get("best_ask")),
        )
    quote_consistency = _clamp01(quote_consistency, default=0.5)
    book_score = quote_consistency
    total_weight = max(flow_weight + book_weight, 1e-6)
    score = _weighted_average(
        [
            (flow_score, flow_weight / total_weight),
            (book_score, book_weight / total_weight),
        ],
        default=0.5,
    )
    if quote_ok is False:
        score *= 0.8
        reasons.append("quote_not_ok")

    score_inputs_used["volume"] = volume if volume > 0.0 else None
    score_inputs_used["oi"] = oi if oi > 0.0 else None
    score_inputs_used["quote_consistency_score"] = quote_consistency
    score_inputs_used["liquidity_flow_score"] = _round_score(flow_score)
    score_inputs_used["liquidity_book_score"] = _round_score(book_score)
    return _clamp01(score, default=0.5), reasons


def _spread_score(candidate: dict[str, Any], market_data: dict[str, Any], score_inputs_used: dict[str, Any]) -> tuple[float, list[str]]:
    spread_pct = _first_float(candidate.get("spread_pct"), market_data.get("spread_pct"))
    if spread_pct is None:
        bid = _first_float(candidate.get("best_bid"), candidate.get("bid"), candidate.get("opt_bid"), market_data.get("best_bid"))
        ask = _first_float(candidate.get("best_ask"), candidate.get("ask"), candidate.get("opt_ask"), market_data.get("best_ask"))
        reference = _first_float(candidate.get("current_ltp"), market_data.get("current_ltp"), candidate.get("opt_ltp"))
        if bid is not None and ask is not None and reference not in (None, 0.0):
            spread_pct = max(0.0, float(ask) - float(bid)) / max(float(reference), 1e-6)
            score_inputs_used["derived_spread_from_bbo"] = True
    max_spread = max(_cfg_float("CANDIDATE_SCORING_MAX_SPREAD_PCT", 0.02), 1e-6)
    if spread_pct is None:
        score_inputs_used["spread_pct"] = None
        return 0.5, ["missing_spread_context"]
    score_inputs_used["spread_pct"] = spread_pct
    return _clamp01(1.0 - min(float(spread_pct) / max_spread, 1.0), default=0.5), []


def _rr_score(candidate: dict[str, Any], market_data: dict[str, Any], score_inputs_used: dict[str, Any]) -> tuple[float, list[str]]:
    entry_basis = _first_float(
        candidate.get("entry_price"),
        candidate.get("expected_entry"),
        candidate.get("entry"),
        market_data.get("reference_price"),
        candidate.get("validation_reference_price"),
        candidate.get("current_ltp"),
        market_data.get("current_ltp"),
    )
    stop_price = _first_float(candidate.get("stop_price"), candidate.get("stop"), candidate.get("stop_loss"))
    target_price = _first_float(candidate.get("target_price"), candidate.get("target"))
    fallback_reason: str | None = None
    if (
        entry_basis is not None
        and (stop_price is None or target_price is None)
        and _cfg_bool("CANDIDATE_SCORING_RR_FALLBACK_ENABLE", True)
    ):
        direction_hint = str(candidate.get("side") or candidate.get("direction") or "").strip().upper()
        buy_side = not any(token in direction_hint for token in ("SELL", "SHORT"))
        if stop_price is None:
            if buy_side:
                stop_mult = _cfg_float("CANDIDATE_SCORING_RR_FALLBACK_BUY_STOP_MULT", 0.75)
            else:
                stop_mult = _cfg_float("CANDIDATE_SCORING_RR_FALLBACK_SELL_STOP_MULT", 1.25)
            stop_price = float(entry_basis) * float(stop_mult)
        if target_price is None:
            if buy_side:
                target_mult = _cfg_float("CANDIDATE_SCORING_RR_FALLBACK_BUY_TARGET_MULT", 1.35)
            else:
                target_mult = _cfg_float("CANDIDATE_SCORING_RR_FALLBACK_SELL_TARGET_MULT", 0.65)
            target_price = float(entry_basis) * float(target_mult)
        fallback_reason = "rr_estimated_context"

    if entry_basis is None or stop_price is None or target_price is None:
        score_inputs_used["rr_basis"] = {
            "entry_basis": entry_basis,
            "stop_price": stop_price,
            "target_price": target_price,
        }
        return 0.45, ["missing_rr_context"]

    reward = abs(float(target_price) - float(entry_basis))
    risk = max(abs(float(entry_basis) - float(stop_price)), 1e-6)
    rr_ratio = reward / risk
    if fallback_reason:
        score_inputs_used["rr_source"] = "fallback_estimated"
    score_inputs_used["rr_ratio"] = rr_ratio
    if rr_ratio >= 3.0:
        score = 1.0
    elif rr_ratio >= 2.0:
        score = 0.85
    elif rr_ratio >= 1.5:
        score = 0.7
    elif rr_ratio >= 1.2:
        score = 0.55
    elif rr_ratio >= 1.0:
        score = 0.4
    else:
        score = 0.22
    reasons: list[str] = []
    if fallback_reason:
        reasons.append(fallback_reason)
    return _clamp01(score, default=0.45), reasons


def _timing_score(candidate: dict[str, Any], market_data: dict[str, Any], context: dict[str, Any], score_inputs_used: dict[str, Any]) -> tuple[float, list[str]]:
    quote_age = _first_float(
        market_data.get("quote_age_sec"),
        candidate.get("quote_age_sec"),
        candidate.get("price_age_sec"),
        candidate.get("option_age_sec"),
    )
    quote_source = str(
        market_data.get("quote_source")
        or candidate.get("option_ltp_source")
        or candidate.get("quote_source")
        or context.get("quote_source")
        or ""
    ).strip().lower()
    market_open = bool(context.get("market_open", market_data.get("market_open", candidate.get("market_open", True))))
    max_age = max(
        _cfg_float("CANDIDATE_SCORING_TIMING_MAX_AGE_SEC", 300.0),
        _cfg_float("OPTION_LTP_SLA_SEC", 2.0),
    )

    score_inputs_used["quote_source"] = quote_source or None
    score_inputs_used["quote_age_sec"] = quote_age
    score_inputs_used["timing_market_open"] = market_open

    if quote_age is None:
        if not market_open and quote_source in {"synthetic_offhours", "rest_fallback", "subscription_failed"}:
            return 0.58, ["missing_live_timing_context"]
        return 0.55, ["missing_timing_context"]

    score = _clamp01(1.0 - min(float(quote_age) / max_age, 1.0), default=0.55)
    if not market_open and quote_source in {"synthetic_offhours", "rest_fallback", "subscription_failed"}:
        score = max(0.5, min(score, 0.65))
    return score, []


def _penalty_score(
    candidate: dict[str, Any],
    context: dict[str, Any],
    *,
    regime_fit: float,
    liquidity_score: float,
    spread_score: float,
    rr_score: float,
    timing_score: float,
    missing_reasons: list[str],
) -> tuple[float, list[str]]:
    hard_blockers = _dedupe_texts(
        _as_list(candidate.get("hard_blockers")) + _as_list(context.get("hard_blockers"))
    )
    soft_penalties = _dedupe_texts(
        _as_list(candidate.get("soft_penalties")) + _as_list(context.get("soft_penalties"))
    )
    warnings = _dedupe_texts(_as_list(candidate.get("warnings")) + _as_list(context.get("warnings")))
    blockers = _dedupe_texts(_as_list(candidate.get("blockers")) + _as_list(context.get("blockers")))
    reasons: list[str] = []

    penalty = 0.0
    hard_weight = _cfg_float("CANDIDATE_SCORING_PENALTY_HARD", 0.18)
    soft_weight = _cfg_float("CANDIDATE_SCORING_PENALTY_SOFT", 0.07)
    warning_weight = _cfg_float("CANDIDATE_SCORING_PENALTY_WARNING", 0.03)
    missing_weight = _cfg_float("CANDIDATE_SCORING_PENALTY_MISSING_CONTEXT", 0.025)

    for code in hard_blockers:
        penalty += hard_weight
        reasons.append(code)
    for code in soft_penalties:
        penalty += soft_weight
        reasons.append(code)
    for code in warnings:
        penalty += warning_weight
        reasons.append(code)
    if candidate.get("unresolved_contract"):
        penalty += hard_weight
        reasons.append("unresolved_contract")
    token = candidate.get("instrument_token")
    if token in (None, "", "None", 0):
        penalty += 0.08
        reasons.append("missing_instrument_token")

    penalty += missing_weight * len(missing_reasons)
    reasons.extend(missing_reasons)

    if regime_fit < 0.4:
        penalty += 0.06
        reasons.append("hostile_regime_fit")
    if liquidity_score < 0.35:
        penalty += 0.05
        reasons.append("thin_liquidity")
    if spread_score < 0.35:
        penalty += 0.05
        reasons.append("wide_spread")
    if rr_score < 0.35:
        penalty += 0.06
        reasons.append("weak_risk_reward")
    if timing_score < 0.35:
        penalty += 0.04
        reasons.append("weak_timing")
    if blockers and not hard_blockers and not soft_penalties and not warnings:
        penalty += 0.03
        reasons.append("uncategorized_blockers")

    max_penalty = _cfg_float("CANDIDATE_SCORING_MAX_PENALTY", 0.6)
    return _clamp01(min(penalty, max_penalty), default=0.0), _dedupe_texts(reasons)


def _crowding_penalty(candidate: dict[str, Any], score_inputs_used: dict[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    correlation_penalty = _normalize_unit(candidate.get("correlation_penalty"))
    if correlation_penalty is not None:
        score_inputs_used["correlation_penalty"] = candidate.get("correlation_penalty")

    duplicate_candidate_count = int(max(_safe_float(candidate.get("duplicate_candidate_count")) or 0.0, 0.0))
    duplicate_group_count = int(max(_safe_float(candidate.get("duplicate_group_count")) or 0.0, 0.0))
    correlated_family_count = int(max(_safe_float(candidate.get("family_conflict_count")) or 0.0, 0.0))
    same_symbol_count = int(max(_safe_float(candidate.get("same_symbol_candidate_count")) or 0.0, 0.0))

    penalty = 0.0
    if correlation_penalty is not None and correlation_penalty > 0.0:
        penalty += min(0.22, correlation_penalty * 0.22)
        reasons.append("correlated_concentration")
    if duplicate_candidate_count > 0:
        penalty += min(0.16, 0.04 * duplicate_candidate_count)
        reasons.append("duplicate_candidate_cluster")
    if duplicate_group_count > 0:
        penalty += min(0.08, 0.02 * duplicate_group_count)
        reasons.append("duplicate_setup_group")
    if correlated_family_count > 0:
        penalty += min(0.10, 0.03 * correlated_family_count)
        reasons.append("family_conflict_concentration")
    if same_symbol_count > 0:
        penalty += min(0.06, 0.02 * same_symbol_count)
        reasons.append("same_symbol_concentration")

    max_penalty = max(_cfg_float("CANDIDATE_SCORING_MAX_CROWDING_PENALTY", 0.35), 0.0)
    return _clamp01(min(penalty, max_penalty), default=0.0), _dedupe_texts(reasons)


def score_candidate(candidate: dict, market_data: dict, context: dict) -> dict:
    """
    Deterministic, side-effect-free candidate scoring.

    All returned score fields are normalized to the [0.0, 1.0] range.
    Missing noncritical inputs degrade the score toward neutral values rather
    than forcing zero-confidence output.
    """
    row = _as_dict(candidate)
    market = _as_dict(market_data)
    ctx = _as_dict(context)
    score_inputs_used: dict[str, Any] = {}

    setup_strength = _setup_strength(row, score_inputs_used)
    regime_fit = _regime_fit(row, market, score_inputs_used)
    liquidity_score, liquidity_reasons = _liquidity_score(row, market, score_inputs_used)
    spread_score, spread_reasons = _spread_score(row, market, score_inputs_used)
    rr_score, rr_reasons = _rr_score(row, market, score_inputs_used)
    timing_score, timing_reasons = _timing_score(row, market, ctx, score_inputs_used)

    missing_reasons = _dedupe_texts(liquidity_reasons + spread_reasons + rr_reasons + timing_reasons)
    confidence_raw = _weighted_average(
        [
            (setup_strength, _cfg_float("CANDIDATE_SCORING_WEIGHT_SETUP", 0.28)),
            (regime_fit, _cfg_float("CANDIDATE_SCORING_WEIGHT_REGIME", 0.14)),
            (liquidity_score, _cfg_float("CANDIDATE_SCORING_WEIGHT_LIQUIDITY", 0.16)),
            (spread_score, _cfg_float("CANDIDATE_SCORING_WEIGHT_SPREAD", 0.10)),
            (rr_score, _cfg_float("CANDIDATE_SCORING_WEIGHT_RR", 0.18)),
            (timing_score, _cfg_float("CANDIDATE_SCORING_WEIGHT_TIMING", 0.14)),
        ],
        default=0.55,
    )
    confluence_score = _weighted_average(
        [
            (setup_strength, 0.45),
            (regime_fit, 0.25),
            (timing_score, 0.30),
        ],
        default=0.55,
    )
    penalty_score, penalty_reasons = _penalty_score(
        row,
        ctx,
        regime_fit=regime_fit,
        liquidity_score=liquidity_score,
        spread_score=spread_score,
        rr_score=rr_score,
        timing_score=timing_score,
        missing_reasons=missing_reasons,
    )
    crowding_penalty, crowding_reasons = _crowding_penalty(row, score_inputs_used)
    penalty_score = _clamp01(penalty_score + crowding_penalty, default=penalty_score)
    penalty_reasons = _dedupe_texts(list(penalty_reasons) + crowding_reasons)
    penalty_weight = _cfg_float("CANDIDATE_SCORING_PENALTY_WEIGHT", 0.45)
    confidence_final = _clamp01(confidence_raw - (penalty_score * penalty_weight), default=confidence_raw)
    rank_score = _weighted_average(
        [
            (confidence_final, 0.55),
            (setup_strength, 0.15),
            (rr_score, 0.12),
            (liquidity_score, 0.10),
            (spread_score, 0.04),
            (timing_score, 0.04),
        ],
        default=confidence_final,
    )
    opportunity_score = _weighted_average(
        [
            (confidence_final, 0.42),
            (setup_strength, 0.16),
            (regime_fit, 0.10),
            (liquidity_score, 0.10),
            (spread_score, 0.06),
            (rr_score, 0.11),
            (timing_score, 0.05),
        ],
        default=confidence_final,
    )

    row_kind = str(row.get("row_kind") or "").strip().lower()
    candidate_class = "primary"
    if row_kind in {"recovered_fallback", "fallback"}:
        candidate_class = "fallback"

    if candidate_class == "fallback":
        cap = _cfg_float("FALLBACK_CANDIDATE_SCORE_CAP", 0.39)
        cap = max(0.0, min(1.0, float(cap)))
        if rank_score > cap:
            rank_score = cap
        if opportunity_score > cap:
            opportunity_score = cap
        penalty_reasons = _dedupe_texts(list(penalty_reasons) + ["class_fallback"])

    score_breakdown = {
        "components": {
            "setup_strength": _round_score(setup_strength),
            "regime_fit": _round_score(regime_fit),
            "liquidity_score": _round_score(liquidity_score),
            "spread_score": _round_score(spread_score),
            "rr_score": _round_score(rr_score),
            "timing_score": _round_score(timing_score),
            "confluence_score": _round_score(confluence_score),
            "penalty_score": _round_score(penalty_score),
            "crowding_penalty": _round_score(crowding_penalty),
        },
        "weights": {
            "setup_strength": _round_score(_cfg_float("CANDIDATE_SCORING_WEIGHT_SETUP", 0.28)),
            "regime_fit": _round_score(_cfg_float("CANDIDATE_SCORING_WEIGHT_REGIME", 0.14)),
            "liquidity_score": _round_score(_cfg_float("CANDIDATE_SCORING_WEIGHT_LIQUIDITY", 0.16)),
            "spread_score": _round_score(_cfg_float("CANDIDATE_SCORING_WEIGHT_SPREAD", 0.10)),
            "rr_score": _round_score(_cfg_float("CANDIDATE_SCORING_WEIGHT_RR", 0.18)),
            "timing_score": _round_score(_cfg_float("CANDIDATE_SCORING_WEIGHT_TIMING", 0.14)),
            "penalty_weight": _round_score(penalty_weight),
        },
        "confidence_raw": _round_score(confidence_raw),
        "confidence_final": _round_score(confidence_final),
        "rank_score": _round_score(rank_score),
        "opportunity_score": _round_score(opportunity_score),
        "missing_reasons": list(missing_reasons),
        "candidate_class": candidate_class,
    }

    return {
        "candidate_class": candidate_class,
        "setup_strength": _round_score(setup_strength),
        "regime_fit": _round_score(regime_fit),
        "liquidity_score": _round_score(liquidity_score),
        "spread_score": _round_score(spread_score),
        "rr_score": _round_score(rr_score),
        "timing_score": _round_score(timing_score),
        "penalty_score": _round_score(penalty_score),
        "crowding_penalty": _round_score(crowding_penalty),
        "confidence_raw": _round_score(confidence_raw),
        "confidence_final": _round_score(confidence_final),
        "rank_score": _round_score(rank_score),
        "opportunity_score": _round_score(opportunity_score),
        "score_breakdown": score_breakdown,
        "penalty_reasons": list(penalty_reasons),
        "score_inputs_used": dict(score_inputs_used),
        "confluence_score": _round_score(confluence_score),
    }
