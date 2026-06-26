from __future__ import annotations

from typing import Any
from math import log1p

from core.quote_truth import quote_consistency_score as canonical_quote_consistency_score
from core.regime_canonical import resolve_strategy_regime_label

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


def _regime_text(value: Any) -> str:
    return str(value or "").strip().upper()


def _regime_bias_hint(candidate: dict[str, Any]) -> str | None:
    text = " ".join(
        str(candidate.get(field) or "").strip().lower()
        for field in (
            "direction",
            "side",
            "signal_direction",
            "movement_bias",
            "bias",
            "option_type",
        )
    )
    if any(token in text for token in ("buy_put", "sell_call", "bearish", "short", "down", "pe")):
        return "bearish"
    if any(token in text for token in ("buy_call", "sell_put", "bullish", "long", "up", "ce")):
        return "bullish"
    return None


def _canonical_regime_label(candidate: dict[str, Any], market_data: dict[str, Any]) -> str:
    raw_regime = (
        market_data.get("regime")
        or candidate.get("regime")
        or market_data.get("day_type")
        or candidate.get("day_type")
        or market_data.get("primary_regime")
    )
    text = _regime_text(raw_regime)
    if text in {
        "CHOP",
        "NOISE",
        "UNCLEAR",
        "COMPRESSION",
        "LOW_VOL",
        "LOW_VOLATILITY",
        "VOLATILITY_EXPANSION",
        "TRAP_RISK",
        "EXHAUSTION_RISK",
        "HIGH_VOL",
        "HIGH_VOLATILITY",
        "EVENT",
        "EVENT_DAY",
        "PANIC",
        "PANIC_DAY",
    }:
        return text

    canonical = resolve_strategy_regime_label(
        raw_regime,
        bias=_regime_bias_hint(candidate),
        expiry_context=bool(candidate.get("expiry_context") or market_data.get("expiry_context")),
    )
    if canonical != "UNKNOWN":
        return canonical

    if text in {
        "TREND",
        "TREND_UP",
        "TREND_DOWN",
        "UPTREND",
        "DOWNTREND",
        "BREAKOUT",
        "MOMENTUM",
        "RANGE",
        "RANGE_VOLATILE",
        "MEAN_REVERSION",
        "SIDEWAYS",
        "CHOP",
        "NOISE",
        "UNCLEAR",
        "INCONCLUSIVE",
        "EXPIRY",
        "EXPIRY_DAY",
        "HIGH_VOL",
        "HIGH_VOLATILITY",
        "LOW_VOL",
        "LOW_VOLATILITY",
        "EVENT",
        "EVENT_DAY",
        "PANIC",
        "PANIC_DAY",
        "BEARISH",
        "BULLISH",
        "VOLATILITY_EXPANSION",
        "COMPRESSION",
    }:
        return text
    return canonical


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
    regime = _canonical_regime_label(candidate, market_data)
    market_open = bool(market_data.get("market_open", candidate.get("market_open", True)))
    countertrend = bool(candidate.get("countertrend"))
    score_inputs_used["regime"] = regime or "UNKNOWN"
    score_inputs_used["market_open"] = market_open
    if countertrend:
        score_inputs_used["countertrend"] = True

    if regime in {"TREND", "UPTREND", "DOWNTREND", "TRENDING_UP", "TRENDING_DOWN"}:
        fit = 0.82
    elif regime in {"RANGE", "RANGE_VOLATILE"}:
        fit = 0.64
    elif regime in {"EXPIRY", "EXPIRY_DAY", "EXPIRY_CONTEXT"}:
        fit = 0.48
    elif regime in {"EVENT", "EVENT_DAY", "PANIC", "PANIC_DAY", "VOLATILE"}:
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


def _regime_bucket(value: Any) -> str:
    regime = _regime_text(value)
    if regime in {"TREND", "TREND_UP", "TREND_DOWN", "UPTREND", "DOWNTREND", "BREAKOUT", "MOMENTUM"}:
        return "TREND"
    if regime in {"TRENDING_UP", "TRENDING_DOWN"}:
        return "TREND"
    if regime in {"RANGE", "RANGE_VOLATILE", "MEAN_REVERSION", "SIDEWAYS"}:
        return "RANGE"
    if regime in {"CHOP", "NOISE", "UNCLEAR", "INCONCLUSIVE"}:
        return "CHOP"
    if regime in {"EXPIRY", "EXPIRY_DAY", "EXPIRY_CONTEXT", "ZERO_HERO", "ZERO_HERO_EXPIRY"}:
        return "EXPIRY"
    if regime in {"HIGH_VOL", "HIGH_VOLATILITY", "VOLATILITY_EXPANSION", "VOLATILE", "EVENT", "PANIC"}:
        return "HIGH_VOL"
    if regime in {"LOW_VOL", "LOW_VOLATILITY", "COMPRESSION"}:
        return "LOW_VOL"
    return "UNKNOWN"


def _candidate_regime_archetype(candidate: dict[str, Any]) -> str:
    family_text = " ".join(
        str(candidate.get(field) or "").strip().lower()
        for field in (
            "strategy_family",
            "movement_type",
            "setup_variant",
            "candidate_type",
            "entry_condition",
            "strategy_name",
        )
    )
    if any(token in family_text for token in ("breakout", "momentum", "trend", "pullback", "opening_drive", "opening_range", "compression_breakout", "volatility_expansion", "opening_drive")):
        return "TREND"
    if any(token in family_text for token in ("mean_reversion", "range", "vwap_reclaim", "exhaustion", "reversal")):
        return "RANGE"
    if any(token in family_text for token in ("expiry", "zero_hero", "time_window", "scalp")):
        return "EXPIRY"
    if any(token in family_text for token in ("chop", "no_trade", "noise", "unclear")):
        return "CHOP"
    return "UNKNOWN"


def _regime_weight_profile(
    candidate: dict[str, Any],
    market_data: dict[str, Any],
    score_inputs_used: dict[str, Any],
) -> tuple[dict[str, float], list[str], float]:
    regime_bucket = _regime_bucket(_canonical_regime_label(candidate, market_data))
    archetype = _candidate_regime_archetype(candidate)
    score_inputs_used["regime_bucket"] = regime_bucket
    score_inputs_used["candidate_archetype"] = archetype
    score_inputs_used["regime_profile_applied"] = regime_bucket != "UNKNOWN"

    weights = {
        "setup_strength": 1.0,
        "regime_fit": 1.0,
        "liquidity_score": 1.0,
        "spread_score": 1.0,
        "rr_score": 1.0,
        "timing_score": 1.0,
    }
    penalty = 0.0
    reasons: list[str] = []

    if regime_bucket == "TREND":
        if archetype == "TREND":
            weights.update(
                {
                    "setup_strength": 1.18,
                    "regime_fit": 1.20,
                    "liquidity_score": 0.94,
                    "spread_score": 0.94,
                    "rr_score": 1.10,
                    "timing_score": 1.08,
                }
            )
            reasons.append("trend_regime_breakout_momentum_preferred")
        elif archetype == "RANGE":
            weights.update(
                {
                    "setup_strength": 0.86,
                    "regime_fit": 0.84,
                    "liquidity_score": 1.00,
                    "spread_score": 1.00,
                    "rr_score": 0.96,
                    "timing_score": 0.94,
                }
            )
            penalty += 0.06
            reasons.append("trend_regime_range_mismatch")
        elif archetype == "EXPIRY":
            weights.update(
                {
                    "setup_strength": 0.92,
                    "regime_fit": 0.95,
                    "liquidity_score": 1.08,
                    "spread_score": 1.10,
                    "rr_score": 1.04,
                    "timing_score": 1.02,
                }
            )
            penalty += 0.03
            reasons.append("trend_regime_expiry_discounted")
    elif regime_bucket == "RANGE":
        if archetype == "RANGE":
            weights.update(
                {
                    "setup_strength": 1.22,
                    "regime_fit": 1.28,
                    "liquidity_score": 1.06,
                    "spread_score": 1.08,
                    "rr_score": 0.84,
                    "timing_score": 1.08,
                }
            )
            reasons.append("range_regime_mean_reversion_preferred")
        elif archetype == "TREND":
            weights.update(
                {
                    "setup_strength": 0.76,
                    "regime_fit": 0.76,
                    "liquidity_score": 0.98,
                    "spread_score": 0.98,
                    "rr_score": 0.82,
                    "timing_score": 0.90,
                }
            )
            penalty += 0.20
            reasons.append("range_regime_breakout_penalty")
        elif archetype == "EXPIRY":
            weights.update(
                {
                    "setup_strength": 0.96,
                    "regime_fit": 1.00,
                    "liquidity_score": 1.14,
                    "spread_score": 1.16,
                    "rr_score": 1.05,
                    "timing_score": 1.08,
                }
            )
            reasons.append("range_regime_expiry_liquidity_sensitive")
    elif regime_bucket == "CHOP":
        weights.update(
            {
                "setup_strength": 0.30,
                "regime_fit": 0.34,
                "liquidity_score": 1.20,
                "spread_score": 1.18,
                "rr_score": 0.58,
                "timing_score": 1.16,
            }
        )
        if archetype in {"TREND", "RANGE"}:
            penalty += 1.0
            reasons.append("chop_regime_directional_penalty")
        else:
            penalty += 0.60
            reasons.append("chop_regime_uncertainty_penalty")
    elif regime_bucket == "EXPIRY":
        weights.update(
            {
                "setup_strength": 0.90,
                "regime_fit": 0.96,
                "liquidity_score": 1.25,
                "spread_score": 1.28,
                "rr_score": 1.15,
                "timing_score": 1.14,
            }
        )
        if archetype == "EXPIRY":
            reasons.append("expiry_regime_liquidity_and_rr_prioritized")
        else:
            penalty += 0.04
            reasons.append("expiry_regime_non_expiry_discount")
    elif regime_bucket == "HIGH_VOL":
        weights.update(
            {
                "setup_strength": 1.05,
                "regime_fit": 1.10,
                "liquidity_score": 0.98,
                "spread_score": 1.20,
                "rr_score": 1.12,
                "timing_score": 1.12,
            }
        )
        if archetype == "TREND":
            reasons.append("high_vol_trend_requires_volatility_expansion_confirmation")
        else:
            penalty += 0.04
            reasons.append("high_vol_non_expansion_penalty")
    elif regime_bucket == "LOW_VOL":
        weights.update(
            {
                "setup_strength": 0.90 if archetype == "TREND" else 1.05,
                "regime_fit": 0.92 if archetype == "TREND" else 1.08,
                "liquidity_score": 1.10,
                "spread_score": 1.12,
                "rr_score": 1.08 if archetype == "RANGE" else 0.96,
                "timing_score": 1.06,
            }
        )
        if archetype == "TREND":
            penalty += 0.08
            reasons.append("low_vol_weak_breakout_penalty")
        elif archetype == "RANGE":
            reasons.append("low_vol_range_preferred_if_liquid")
        else:
            penalty += 0.04
            reasons.append("low_vol_unclear_penalty")
    else:
        weights.update(
            {
                "setup_strength": 0.96,
                "regime_fit": 0.96,
                "liquidity_score": 1.04,
                "spread_score": 1.04,
                "rr_score": 0.98,
                "timing_score": 1.00,
            }
        )
        penalty += 0.03
        reasons.append("unknown_regime_conservative_profile")

    return weights, reasons, _clamp01(penalty, default=0.0)


def _liquidity_score(candidate: dict[str, Any], market_data: dict[str, Any], context: dict[str, Any], score_inputs_used: dict[str, Any]) -> tuple[float, list[str]]:
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

    trading_mode = str(context.get("trading_mode", market_data.get("trading_mode", "SIM"))).upper()
    if volume <= 0.0 and oi <= 0.0:
        score_inputs_used["liquidity"] = "missing"
        if trading_mode == "LIVE":
            reasons.append("missing_liquidity_context_live_block")
            return 0.0, reasons
        else:
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


def _spread_score(candidate: dict[str, Any], market_data: dict[str, Any], context: dict[str, Any], score_inputs_used: dict[str, Any]) -> tuple[float, list[str]]:
    spread_pct = _first_float(candidate.get("spread_pct"), market_data.get("spread_pct"))
    if spread_pct is None:
        bid = _first_float(candidate.get("best_bid"), candidate.get("bid"), candidate.get("opt_bid"), market_data.get("best_bid"))
        ask = _first_float(candidate.get("best_ask"), candidate.get("ask"), candidate.get("opt_ask"), market_data.get("best_ask"))
        reference = _first_float(candidate.get("current_ltp"), market_data.get("current_ltp"), candidate.get("opt_ltp"))
        if bid is not None and ask is not None and reference not in (None, 0.0):
            spread_pct = max(0.0, float(ask) - float(bid)) / max(float(reference), 1e-6)
            score_inputs_used["derived_spread_from_bbo"] = True
    trading_mode = str(context.get("trading_mode", market_data.get("trading_mode", "SIM"))).upper()
    max_spread = max(_cfg_float("CANDIDATE_SCORING_MAX_SPREAD_PCT", 0.02), 1e-6)
    if spread_pct is None:
        score_inputs_used["spread_pct"] = None
        if trading_mode == "LIVE":
            return 0.0, ["missing_spread_context_live_block"]
        else:
            return 0.5, ["missing_spread_context"]
    score_inputs_used["spread_pct"] = spread_pct
    return _clamp01(1.0 - min(float(spread_pct) / max_spread, 1.0), default=0.5), []


def _rr_score(candidate: dict[str, Any], market_data: dict[str, Any], context: dict[str, Any], score_inputs_used: dict[str, Any]) -> tuple[float, list[str]]:
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
    trading_mode = str(context.get("trading_mode", market_data.get("trading_mode", "SIM"))).upper()
    fallback_enabled = _cfg_bool("CANDIDATE_SCORING_RR_FALLBACK_ENABLE_PAPER", True) if trading_mode in ("PAPER", "SIM") else _cfg_bool("CANDIDATE_SCORING_RR_FALLBACK_ENABLE_LIVE", False)
    
    if (
        entry_basis is not None
        and (stop_price is None or target_price is None)
        and fallback_enabled
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
        if trading_mode == "LIVE":
            return 0.0, ["missing_rr_context_live_block"]
        else:
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
    trading_mode = str(context.get("trading_mode", market_data.get("trading_mode", "SIM"))).upper()
    
    if trading_mode == "LIVE":
        max_age = max(
            _cfg_float("LIVE_OPTION_LTP_MAX_AGE_SEC", 2.0),
            _cfg_float("OPTION_LTP_SLA_SEC", 2.0),
        )
    elif trading_mode in ("PAPER", "SIM"):
        max_age = max(
            _cfg_float("PAPER_OPTION_LTP_MAX_AGE_SEC", 5.0),
            _cfg_float("OPTION_LTP_SLA_SEC", 2.0),
        )
    else:
        max_age = max(
            _cfg_float("OFFHOURS_DIAGNOSTIC_MAX_AGE_SEC", 300.0),
            _cfg_float("CANDIDATE_SCORING_TIMING_MAX_AGE_SEC", 300.0),
        )

    score_inputs_used["quote_source"] = quote_source or None
    score_inputs_used["quote_age_sec"] = quote_age
    score_inputs_used["timing_market_open"] = market_open

    if quote_age is None:
        if not market_open and quote_source in {"synthetic_offhours", "rest_fallback", "subscription_failed"}:
            return 0.58, ["missing_live_timing_context"]
        if trading_mode == "LIVE":
            return 0.0, ["missing_timing_context_live_block"]
        return 0.55, ["missing_timing_context"]

    score = _clamp01(1.0 - min(float(quote_age) / max_age, 1.0), default=0.55)
    if not market_open and quote_source in {"synthetic_offhours", "rest_fallback", "subscription_failed"}:
        score = max(0.5, min(score, 0.65))
    if trading_mode == "LIVE" and score <= 0.0:
        return 0.0, ["stale_quote_age_live_block"]
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

    for missing_reason in missing_reasons:
        if missing_reason.endswith("_live_block"):
            penalty += hard_weight
            reasons.append(missing_reason)
        else:
            penalty += missing_weight
            reasons.append(missing_reason)

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
    liquidity_score, liquidity_reasons = _liquidity_score(row, market, ctx, score_inputs_used)
    spread_score, spread_reasons = _spread_score(row, market, ctx, score_inputs_used)
    rr_score, rr_reasons = _rr_score(row, market, ctx, score_inputs_used)
    timing_score, timing_reasons = _timing_score(row, market, ctx, score_inputs_used)
    regime_weights, regime_reasons, regime_penalty = _regime_weight_profile(row, market, score_inputs_used)

    missing_reasons = _dedupe_texts(liquidity_reasons + spread_reasons + rr_reasons + timing_reasons)
    confidence_raw = _weighted_average(
        [
            (setup_strength, _cfg_float("CANDIDATE_SCORING_WEIGHT_SETUP", 0.28) * regime_weights["setup_strength"]),
            (regime_fit, _cfg_float("CANDIDATE_SCORING_WEIGHT_REGIME", 0.14) * regime_weights["regime_fit"]),
            (liquidity_score, _cfg_float("CANDIDATE_SCORING_WEIGHT_LIQUIDITY", 0.16) * regime_weights["liquidity_score"]),
            (spread_score, _cfg_float("CANDIDATE_SCORING_WEIGHT_SPREAD", 0.10) * regime_weights["spread_score"]),
            (rr_score, _cfg_float("CANDIDATE_SCORING_WEIGHT_RR", 0.18) * regime_weights["rr_score"]),
            (timing_score, _cfg_float("CANDIDATE_SCORING_WEIGHT_TIMING", 0.14) * regime_weights["timing_score"]),
        ],
        default=0.55,
    )
    confluence_score = _weighted_average(
        [
            (setup_strength, 0.45 * regime_weights["setup_strength"]),
            (regime_fit, 0.25 * regime_weights["regime_fit"]),
            (timing_score, 0.30 * regime_weights["timing_score"]),
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
    penalty_score = _clamp01(penalty_score + crowding_penalty + regime_penalty, default=penalty_score)
    penalty_reasons = _dedupe_texts(list(penalty_reasons) + crowding_reasons + regime_reasons)
    penalty_weight = _cfg_float("CANDIDATE_SCORING_PENALTY_WEIGHT", 0.45)
    confidence_final = _clamp01(confidence_raw - (penalty_score * penalty_weight), default=confidence_raw)
    rank_score = _weighted_average(
        [
            (confidence_final, 0.55),
            (setup_strength, 0.15 * regime_weights["setup_strength"]),
            (rr_score, 0.12 * regime_weights["rr_score"]),
            (liquidity_score, 0.10 * regime_weights["liquidity_score"]),
            (spread_score, 0.04 * regime_weights["spread_score"]),
            (timing_score, 0.04 * regime_weights["timing_score"]),
        ],
        default=confidence_final,
    )
    opportunity_score = _weighted_average(
        [
            (confidence_final, 0.42),
            (setup_strength, 0.16 * regime_weights["setup_strength"]),
            (regime_fit, 0.10 * regime_weights["regime_fit"]),
            (liquidity_score, 0.10 * regime_weights["liquidity_score"]),
            (spread_score, 0.06 * regime_weights["spread_score"]),
            (rr_score, 0.11 * regime_weights["rr_score"]),
            (timing_score, 0.05 * regime_weights["timing_score"]),
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
        "regime_profile": {
            "regime_bucket": score_inputs_used.get("regime_bucket"),
            "candidate_archetype": score_inputs_used.get("candidate_archetype"),
            "weights": dict(regime_weights),
            "penalty": _round_score(regime_penalty),
            "reasons": list(regime_reasons),
        },
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
        "regime_profile": {
            "regime_bucket": score_inputs_used.get("regime_bucket"),
            "candidate_archetype": score_inputs_used.get("candidate_archetype"),
            "weights": dict(regime_weights),
            "penalty": _round_score(regime_penalty),
            "reasons": list(regime_reasons),
        },
    }
