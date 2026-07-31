from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha1
from typing import Any, Mapping

from core.candidate_exposure import (
    EXPOSURE_BEARISH,
    EXPOSURE_BULLISH,
    EXPOSURE_RANGE,
    EXPOSURE_UNKNOWN,
    SETUP_DIRECTIONAL,
    SETUP_RANGE_COMPATIBLE,
    normalize_directional_exposure,
)
from core.regime_canonical import resolve_strategy_regime_label
from .expectancy_gate import (
    EXPECTANCY_INSUFFICIENT_DATA,
    EXPECTANCY_KEEP,
    EXPECTANCY_KILL,
    EXPECTANCY_WATCH,
)
from .setup_fingerprint import build_setup_fingerprint

EDGE_RANK_SCHEMA_VERSION = 1

_STATUS_BASE_SCORE = {
    EXPECTANCY_KILL: 0.0,
    EXPECTANCY_INSUFFICIENT_DATA: 0.18,
    EXPECTANCY_WATCH: 0.54,
    EXPECTANCY_KEEP: 0.92,
}

_STATUS_CAP = {
    EXPECTANCY_KILL: 0.0,
    EXPECTANCY_INSUFFICIENT_DATA: 0.30,
    EXPECTANCY_WATCH: 0.55,
    EXPECTANCY_KEEP: 1.0,
}

_FALLBACK_MARKER_QUOTE_SOURCES = {
    "REST_FALLBACK",
    "SYNTHETIC_OFFHOURS",
    "SUBSCRIPTION_FAILED",
}

_FRESHNESS_BLOCKER_TOKENS = {
    "STALE",
    "LTP_STALE",
    "STALE_OPTION_LTP",
    "FEED_LTP_STALE",
    "FEED_DEPTH_STALE",
    "WS_DISCONNECTED",
    "GLOBAL_FEED_UNHEALTHY",
    "RECOVERY_BLOCKED",
    "LATENCY_GUARD_HALT_ALL",
    "LATENCY_GUARD_HALT",
    "LATENCY_BREACH",
    "WS1006",
    "PROCESS_RESTART_REQUIRED",
    "FEED_WS_PROCESS_RESTART_REQUIRED",
    "NO_LIVE_OPTION_FEED",
}


@dataclass(frozen=True)
class EdgeRankDecision:
    schema_version: int
    edge_rank_score: float
    edge_rank_reason: str
    edge_rank_components: dict[str, Any]
    expectancy_score: float
    expectancy_status: str
    expectancy_sample_count: int
    expectancy_avg_cost_adjusted_r: float | None
    baseline_verdict: str = "MATCHES"
    baseline_penalty_or_boost: float = 0.0
    baseline_source: str = "missing_baseline"
    baseline_reason: str = ""
    read_only: bool = True
    append: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _int(value: Any) -> int | None:
    try:
        if value in (None, "", "None"):
            return None
        return int(float(value))
    except Exception:
        return None


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        candidate = to_dict()
        if isinstance(candidate, Mapping):
            return candidate
    return {}


def _regime_bias_hint(row: Mapping[str, Any]) -> str | None:
    text = " ".join(
        _lower(row.get(field))
        for field in ("direction", "side", "signal_direction", "movement_bias", "bias", "option_type")
    )
    if any(token in text for token in ("buy_put", "sell_call", "bearish", "short", "down", "pe")):
        return "bearish"
    if any(token in text for token in ("buy_call", "sell_put", "bullish", "long", "up", "ce")):
        return "bullish"
    return None


def _canonical_regime_label(row: Mapping[str, Any]) -> str:
    raw_regime = (
        row.get("regime")
        or row.get("primary_regime")
        or row.get("day_type")
        or row.get("market_regime")
    )
    canonical = resolve_strategy_regime_label(
        raw_regime,
        bias=_regime_bias_hint(row),
        expiry_context=bool(row.get("expiry_context")),
    )
    if canonical != "UNKNOWN":
        return canonical

    text = _upper(raw_regime)
    if text in {
        "BEARISH",
        "BULLISH",
        "TREND",
        "TREND_UP",
        "TREND_DOWN",
        "RANGE",
        "SIDEWAYS",
        "CHOP",
        "NOISE",
        "UNCLEAR",
        "VOLATILE",
        "UNKNOWN",
    }:
        return text
    return canonical


def _stable_setup_id(row: Mapping[str, Any]) -> str:
    setup_id = _text(row.get("setup_id"))
    if setup_id:
        return setup_id
    try:
        return build_setup_fingerprint(row).setup_id
    except Exception:
        canonical = "|".join(
            [
                _text(row.get("strategy_family")),
                _text(row.get("regime")),
                _text(row.get("index")),
                _text(row.get("expiry_type")),
                _text(row.get("option_type")),
                _text(row.get("direction") or row.get("side")),
                _text(row.get("volatility_bucket")),
                _text(row.get("volume_bucket")),
                _text(row.get("spread_bucket")),
                _text(row.get("time_of_day_bucket")),
            ]
        )
        return sha1(canonical.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def _lookup_candidates(row: Mapping[str, Any], expectancy_lookup: Any = None) -> list[Any]:
    lookup_value = expectancy_lookup
    if lookup_value is None:
        lookup_value = row.get("expectancy_lookup")
    if lookup_value is None and isinstance(row.get("metadata"), Mapping):
        lookup_value = (row.get("metadata") or {}).get("expectancy_lookup")
    if lookup_value is None and isinstance(row.get("source_flags"), Mapping):
        lookup_value = (row.get("source_flags") or {}).get("expectancy_lookup")

    if callable(lookup_value):
        return [lookup_value]

    if not isinstance(lookup_value, Mapping):
        return []

    setup_id = _stable_setup_id(row)
    strategy_family = _lower(row.get("strategy_family"))
    regime = _lower(row.get("regime"))
    index = _lower(row.get("index"))
    expiry_type = _lower(row.get("expiry_type"))
    option_type = _lower(row.get("option_type"))
    direction = _lower(row.get("direction") or row.get("side"))

    candidates: list[Any] = []
    if setup_id:
        candidates.append(lookup_value.get(setup_id))
    if setup_id:
        nested = lookup_value.get(strategy_family, {}) if isinstance(lookup_value.get(strategy_family, {}), Mapping) else None
        if isinstance(nested, Mapping):
            nested = nested.get(regime, {})
            if isinstance(nested, Mapping):
                candidates.append(nested.get(setup_id))
    candidates.extend(
        [
            lookup_value.get((strategy_family, regime, setup_id)) if setup_id else None,
            lookup_value.get((strategy_family, regime, index, expiry_type, option_type, direction)),
            lookup_value.get((strategy_family, regime, index)),
            lookup_value.get((strategy_family, regime)),
        ]
    )
    return candidates


def _resolve_expectancy_context(row: Mapping[str, Any], expectancy_lookup: Any = None) -> tuple[str, int, float | None, str]:
    direct_status = _upper(row.get("expectancy_status") or row.get("keep_watch_kill_status"))
    status = direct_status if direct_status in _STATUS_BASE_SCORE else EXPECTANCY_INSUFFICIENT_DATA
    sample_count = _int(row.get("expectancy_sample_count") or row.get("sample_count")) or 0
    avg_cost_adjusted_r = _float(
        row.get("expectancy_avg_cost_adjusted_r")
        if row.get("expectancy_avg_cost_adjusted_r") is not None
        else row.get("avg_cost_adjusted_r")
    )
    reason = "row_expectancy_status" if direct_status in _STATUS_BASE_SCORE else "missing_expectancy_lookup"

    for candidate in _lookup_candidates(row, expectancy_lookup=expectancy_lookup):
        if candidate is None:
            continue
        if callable(candidate):
            resolved = candidate(row)
            if isinstance(resolved, Mapping):
                status = _upper(resolved.get("expectancy_status") or resolved.get("keep_watch_kill_status"))
                if status not in _STATUS_BASE_SCORE:
                    status = EXPECTANCY_INSUFFICIENT_DATA
                sample_count = _int(
                    resolved.get("expectancy_sample_count")
                    if resolved.get("expectancy_sample_count") is not None
                    else resolved.get("sample_count")
                ) or sample_count
                avg_cost_adjusted_r = _float(
                    resolved.get("expectancy_avg_cost_adjusted_r")
                    if resolved.get("expectancy_avg_cost_adjusted_r") is not None
                    else resolved.get("avg_cost_adjusted_r")
                ) if (
                    resolved.get("expectancy_avg_cost_adjusted_r") is not None
                    or resolved.get("avg_cost_adjusted_r") is not None
                ) else avg_cost_adjusted_r
                return status, sample_count, avg_cost_adjusted_r, "callable_expectancy_lookup"
            if resolved is not None:
                status = _upper(resolved)
                if status not in _STATUS_BASE_SCORE:
                    status = EXPECTANCY_INSUFFICIENT_DATA
                return status, sample_count, avg_cost_adjusted_r, "callable_expectancy_lookup"
            continue

        if isinstance(candidate, Mapping):
            resolved_status = _upper(candidate.get("expectancy_status") or candidate.get("keep_watch_kill_status"))
            if resolved_status in _STATUS_BASE_SCORE:
                status = resolved_status
            sample_value = candidate.get("expectancy_sample_count")
            if sample_value is None:
                sample_value = candidate.get("sample_count")
            resolved_sample = _int(sample_value)
            if resolved_sample is not None:
                sample_count = resolved_sample
            avg_value = candidate.get("expectancy_avg_cost_adjusted_r")
            if avg_value is None:
                avg_value = candidate.get("avg_cost_adjusted_r")
            resolved_avg = _float(avg_value)
            if resolved_avg is not None:
                avg_cost_adjusted_r = resolved_avg
            reason = "mapping_expectancy_lookup"
            break

        status = _upper(candidate)
        if status not in _STATUS_BASE_SCORE:
            status = EXPECTANCY_INSUFFICIENT_DATA
        reason = "mapping_expectancy_lookup"
        break

    if status not in _STATUS_BASE_SCORE:
        status = EXPECTANCY_INSUFFICIENT_DATA
        reason = "missing_expectancy_lookup"
    return status, sample_count, avg_cost_adjusted_r, reason


def _resolve_baseline_context(row: Mapping[str, Any], baseline_lookup: Any = None) -> tuple[str, float, str, str]:
    direct_verdict = _upper(row.get("baseline_verdict") or row.get("expectancy_baseline_verdict"))
    direct_adjustment = _float(row.get("baseline_penalty_or_boost") or row.get("expectancy_baseline_penalty_or_boost"))
    direct_source = _text(row.get("baseline_source") or row.get("expectancy_baseline_source")) or "row_baseline"
    direct_reason = _text(row.get("baseline_reason") or row.get("expectancy_baseline_reason"))
    if direct_verdict in {"OUTPERFORMS", "MATCHES", "UNDERPERFORMS", "INSUFFICIENT_SAMPLE"}:
        return direct_verdict, float(direct_adjustment or 0.0), direct_source, direct_reason or "row_baseline"

    lookup_value = baseline_lookup
    if lookup_value is None:
        lookup_value = row.get("baseline_lookup")
    if lookup_value is None and isinstance(row.get("metadata"), Mapping):
        lookup_value = (row.get("metadata") or {}).get("baseline_lookup")
    if lookup_value is None and isinstance(row.get("source_flags"), Mapping):
        lookup_value = (row.get("source_flags") or {}).get("baseline_lookup")

    if callable(lookup_value):
        resolved = lookup_value(row)
        if isinstance(resolved, Mapping):
            verdict = _upper(resolved.get("baseline_verdict"))
            if verdict in {"OUTPERFORMS", "MATCHES", "UNDERPERFORMS", "INSUFFICIENT_SAMPLE"}:
                return (
                    verdict,
                    float(_float(resolved.get("baseline_penalty_or_boost")) or 0.0),
                    _text(resolved.get("baseline_source")) or "callable_baseline_lookup",
                    _text(resolved.get("baseline_reason")) or "callable_baseline_lookup",
                )
        elif resolved is not None:
            verdict = _upper(resolved)
            if verdict in {"OUTPERFORMS", "MATCHES", "UNDERPERFORMS", "INSUFFICIENT_SAMPLE"}:
                return verdict, 0.0, "callable_baseline_lookup", "callable_baseline_lookup"
        return "INSUFFICIENT_SAMPLE", 0.0, "missing_baseline_lookup", "missing_baseline_lookup"

    if isinstance(lookup_value, Mapping):
        setup_id = _stable_setup_id(row)
        strategy_family = _lower(row.get("strategy_family"))
        regime = _lower(row.get("regime"))
        index = _lower(row.get("index"))
        expiry_type = _lower(row.get("expiry_type"))
        option_type = _lower(row.get("option_type"))
        direction = _lower(row.get("direction") or row.get("side"))
        candidates: list[Any] = [
            lookup_value.get(setup_id) if setup_id else None,
            lookup_value.get((strategy_family, regime, setup_id)) if setup_id else None,
            lookup_value.get((strategy_family, regime, index, expiry_type, option_type, direction)),
            lookup_value.get((strategy_family, regime, index)),
            lookup_value.get((strategy_family, regime)),
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            if isinstance(candidate, Mapping):
                verdict = _upper(candidate.get("baseline_verdict"))
                if verdict not in {"OUTPERFORMS", "MATCHES", "UNDERPERFORMS", "INSUFFICIENT_SAMPLE"}:
                    continue
                return (
                    verdict,
                    float(_float(candidate.get("baseline_penalty_or_boost")) or 0.0),
                    _text(candidate.get("baseline_source")) or "mapping_baseline_lookup",
                    _text(candidate.get("baseline_reason")) or "mapping_baseline_lookup",
                )
            verdict = _upper(candidate)
            if verdict in {"OUTPERFORMS", "MATCHES", "UNDERPERFORMS", "INSUFFICIENT_SAMPLE"}:
                return verdict, 0.0, "mapping_baseline_lookup", "mapping_baseline_lookup"
    return "INSUFFICIENT_SAMPLE", 0.0, "missing_baseline_lookup", "missing_baseline_lookup"


def _is_fallback_candidate(row: Mapping[str, Any]) -> bool:
    row_kind = _lower(row.get("row_kind"))
    candidate_class = _lower(row.get("candidate_class"))
    candidate_type = _lower(row.get("candidate_type"))
    candidate_origin = _lower(row.get("candidate_origin"))
    quote_source = _upper(row.get("quote_source"))
    trade_id = _text(row.get("trade_id"))
    fallback_used = bool(row.get("fallback_used"))

    if row_kind in {"recovered_fallback", "fallback"}:
        return True
    if candidate_class == "fallback":
        return True
    if "fallback" in candidate_type:
        return True
    if "fallback" in candidate_origin:
        return True
    if quote_source in _FALLBACK_MARKER_QUOTE_SOURCES:
        return True
    if trade_id.startswith("softrej_"):
        return True
    if fallback_used:
        return True

    source_flags = row.get("source_flags")
    if isinstance(source_flags, Mapping):
        for value in source_flags.values():
            text = _lower(value)
            if any(token in text for token in ("fallback", "recovered", "softened")):
                return True
    return False


def _is_feed_or_stale_blocked(row: Mapping[str, Any]) -> bool:
    feed_truth_state = _upper(row.get("feed_truth_state"))
    runtime_state = _upper(row.get("runtime_state"))
    if feed_truth_state in {"DEAD", "RECOVERY_BLOCKED"}:
        return True
    if runtime_state in {"DEAD", "RECOVERY_BLOCKED"}:
        return True
    if row.get("ws_connected") is False and bool(row.get("process_restart_required")):
        return True
    reconnect_reason = _lower(row.get("reconnect_blocked_reason"))
    if "ws1006_process_restart_required" in reconnect_reason:
        return True
    block_fields = [
        row.get("final_emit_block_reason"),
        row.get("final_blocker"),
        row.get("execution_block_reason"),
        row.get("permission_reason"),
        row.get("hard_reason"),
        row.get("entry_block_code"),
        row.get("entry_block_reason"),
    ]
    block_fields.extend(list(row.get("blockers") or []))
    block_fields.extend(list(row.get("hard_blockers") or []))
    block_fields.extend(list(row.get("soft_penalties") or []))
    block_fields.extend(list(row.get("warnings") or []))
    block_fields.extend(list(row.get("execution_truth_blockers") or []))
    for value in block_fields:
        text = _upper(value)
        if any(token in text for token in _FRESHNESS_BLOCKER_TOKENS):
            return True
    return False


def _float_from_row(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _float(row.get(key))
        if value is not None:
            return value
    score_breakdown = row.get("score_breakdown")
    if isinstance(score_breakdown, Mapping):
        components = score_breakdown.get("components")
        if isinstance(components, Mapping):
            for key in keys:
                value = _float(components.get(key))
                if value is not None:
                    return value
    return None


def _execution_quality(row: Mapping[str, Any]) -> float:
    candidate = _float_from_row(row, "rank_score", "confidence_final", "confidence", "opportunity_score")
    if candidate is None:
        candidate = 0.0
    return _clamp(candidate)


def _liquidity_score(row: Mapping[str, Any]) -> float:
    candidate = _float_from_row(row, "liquidity_score")
    if candidate is None:
        candidate = _float(row.get("spread_score"))
    if candidate is None:
        candidate = 0.0
    return _clamp(candidate)


def _freshness_score(row: Mapping[str, Any]) -> float:
    candidate = _float_from_row(row, "timing_score")
    if candidate is None:
        candidate = _float(row.get("freshness_score"))
    if candidate is None:
        candidate = 0.0
    return _clamp(candidate)


def _regime_match(row: Mapping[str, Any]) -> float:
    candidate = _float_from_row(row, "regime_fit")
    if candidate is None:
        candidate = 0.0
    return _clamp(candidate)


def _risk_reward_score(row: Mapping[str, Any]) -> float:
    candidate = _float_from_row(row, "rr_score", "risk_reward_score")
    if candidate is None:
        candidate = 0.0
    return _clamp(candidate)


def candidate_regime_mismatch_penalty(row: Mapping[str, Any]) -> tuple[float, list[str], dict[str, Any]]:
    exposure = normalize_directional_exposure(row)
    regime = _canonical_regime_label(row)
    strategy_family = _lower(row.get("strategy_family"))
    movement_type = _upper(row.get("movement_type"))
    penalty = 0.0
    reasons: list[str] = []

    if regime in {"TRENDING_DOWN", "BEARISH", "TREND_DOWN"} and exposure.exposure == EXPOSURE_BULLISH:
        penalty += 0.12
        reasons.append("bearish_regime_bullish_exposure")
    if regime in {"RANGE", "SIDEWAYS"} and (
        exposure.setup_kind == SETUP_DIRECTIONAL
        or any(token in strategy_family for token in ("breakout", "momentum", "trend", "pullback"))
        or any(token in movement_type for token in ("BREAKOUT", "MOMENTUM", "TREND", "PULLBACK", "DRIVE"))
    ):
        penalty += 0.12
        reasons.append("range_regime_directional_setup")
    if regime in {"VOLATILE", "CHOP", "NOISE", "UNCLEAR", "UNKNOWN"} and exposure.setup_kind == SETUP_DIRECTIONAL and exposure.exposure in {EXPOSURE_BULLISH, EXPOSURE_BEARISH, EXPOSURE_UNKNOWN}:
        penalty += 0.08
        reasons.append("chop_regime_directional_setup" if regime != "VOLATILE" else "volatile_regime_directional_caution")

    penalty = _clamp(penalty, 0.0, 0.20)
    components = {
        "canonical_regime": regime,
        "candidate_exposure": exposure.exposure,
        "candidate_setup_kind": exposure.setup_kind,
        "candidate_exposure_confidence": _round(exposure.confidence),
        "candidate_exposure_evidence": list(exposure.evidence),
    }
    return penalty, reasons, components


def _crowding_penalty(row: Mapping[str, Any]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    penalty = 0.0

    correlation_penalty = _float(row.get("correlation_penalty"))
    if correlation_penalty is not None and correlation_penalty > 0.0:
        penalty += min(0.20, correlation_penalty * 0.20)
        reasons.append("correlated_concentration")

    family_consensus_score = _float(row.get("family_consensus_score"))
    if family_consensus_score is not None:
        if family_consensus_score < 0.35:
            penalty += 0.04
            reasons.append("weak_family_consensus")
        elif family_consensus_score < 0.55:
            penalty += 0.02
            reasons.append("moderate_family_consensus")

    duplicate_candidate_count = int(max(_float(row.get("duplicate_candidate_count")) or 0.0, 0.0))
    duplicate_group_count = int(max(_float(row.get("duplicate_group_count")) or 0.0, 0.0))
    same_symbol_count = int(max(_float(row.get("same_symbol_candidate_count")) or 0.0, 0.0))
    if duplicate_candidate_count > 0:
        penalty += min(0.16, 0.04 * duplicate_candidate_count)
        reasons.append("duplicate_candidate_cluster")
    if duplicate_group_count > 0:
        penalty += min(0.08, 0.02 * duplicate_group_count)
        reasons.append("duplicate_setup_group")
    if same_symbol_count > 0:
        penalty += min(0.06, 0.02 * same_symbol_count)
        reasons.append("same_symbol_concentration")

    return _clamp(penalty, 0.0, 0.35), reasons


def _expectancy_score(status: str, sample_count: int, avg_cost_adjusted_r: float | None) -> float:
    base = _STATUS_BASE_SCORE.get(status, _STATUS_BASE_SCORE[EXPECTANCY_INSUFFICIENT_DATA])
    if status == EXPECTANCY_KILL:
        return 0.0
    sample_bonus = min(max(sample_count, 0) / 100.0, 0.08)
    avg_bonus = 0.0
    if avg_cost_adjusted_r is not None:
        avg_bonus = _clamp((avg_cost_adjusted_r + 0.10) * 0.25, 0.0, 0.12)
    return _clamp(base + sample_bonus + avg_bonus)


def _score_components(
    row: Mapping[str, Any],
    *,
    status: str,
    sample_count: int,
    avg_cost_adjusted_r: float | None,
) -> tuple[float, dict[str, float]]:
    expectancy_score = _expectancy_score(status, sample_count, avg_cost_adjusted_r)
    execution_quality = _execution_quality(row)
    liquidity_score = _liquidity_score(row)
    freshness_score = _freshness_score(row)
    regime_match = _regime_match(row)
    risk_reward_score = _risk_reward_score(row)
    crowding_penalty, crowding_reasons = _crowding_penalty(row)
    regime_mismatch_penalty, regime_mismatch_reasons, regime_mismatch_components = candidate_regime_mismatch_penalty(row)
    raw_score = (
        expectancy_score * 0.40
        + execution_quality * 0.20
        + liquidity_score * 0.12
        + freshness_score * 0.10
        + regime_match * 0.10
        + risk_reward_score * 0.08
    )
    raw_score = max(0.0, raw_score - crowding_penalty - regime_mismatch_penalty)
    return raw_score, {
        "expectancy_score": _round(expectancy_score),
        "execution_quality": _round(execution_quality),
        "liquidity_score": _round(liquidity_score),
        "freshness_score": _round(freshness_score),
        "regime_match": _round(regime_match),
        "risk_reward_score": _round(risk_reward_score),
        "crowding_penalty": _round(crowding_penalty),
        "crowding_reasons": list(crowding_reasons),
        "candidate_regime_mismatch_penalty": _round(regime_mismatch_penalty),
        "candidate_regime_mismatch_reasons": list(regime_mismatch_reasons),
        "raw_edge_rank_score": _round(raw_score),
        **regime_mismatch_components,
    }


def _build_reason(
    *,
    status: str,
    capped: bool,
    fallback_candidate: bool,
    feed_blocked: bool,
    regime_mismatch_reasons: list[str] | None = None,
    crowding_reasons: list[str] | None = None,
) -> str:
    reasons: list[str] = []
    if fallback_candidate:
        reasons.append("fallback_not_rankable")
    if feed_blocked:
        reasons.append("feed_truth_blocked")
    if regime_mismatch_reasons:
        reasons.extend(regime_mismatch_reasons)
    if crowding_reasons:
        reasons.extend(crowding_reasons)
    if status == EXPECTANCY_KILL:
        reasons.append("expectancy_kill")
    elif status == EXPECTANCY_INSUFFICIENT_DATA:
        reasons.append("expectancy_insufficient_data")
    elif status == EXPECTANCY_WATCH:
        reasons.append("expectancy_watch")
    elif status == EXPECTANCY_KEEP:
        reasons.append("expectancy_keep")
    if capped:
        reasons.append("status_capped")
    if not reasons:
        reasons.append("edge_ranked")
    return "|".join(reasons)


def apply_edge_ranking(entry: Mapping[str, Any] | dict[str, Any], expectancy_lookup: Any = None) -> dict[str, Any]:
    if not isinstance(entry, Mapping):
        return dict(entry or {})

    row = dict(entry)
    status, sample_count, avg_cost_adjusted_r, reason_source = _resolve_expectancy_context(row, expectancy_lookup=expectancy_lookup)
    baseline_verdict, baseline_penalty_or_boost, baseline_source, baseline_reason = _resolve_baseline_context(row, baseline_lookup=expectancy_lookup)
    fallback_candidate = _is_fallback_candidate(row)
    feed_blocked = _is_feed_or_stale_blocked(row)

    raw_score, components = _score_components(
        row,
        status=status,
        sample_count=sample_count,
        avg_cost_adjusted_r=avg_cost_adjusted_r,
    )
    if status == EXPECTANCY_KEEP and not fallback_candidate and not feed_blocked:
        raw_score = max(0.0, raw_score + baseline_penalty_or_boost)
        components["raw_edge_rank_score"] = _round(raw_score)

    if status == EXPECTANCY_KILL or fallback_candidate or feed_blocked:
        edge_rank_score = 0.0
        capped = True
    else:
        cap = _STATUS_CAP.get(status, 0.30)
        capped = raw_score > cap + 1e-9
        edge_rank_score = min(raw_score, cap)

    components.update(
        {
            "schema_version": EDGE_RANK_SCHEMA_VERSION,
        "expectancy_status": status,
        "expectancy_sample_count": sample_count,
        "expectancy_avg_cost_adjusted_r": _round(avg_cost_adjusted_r),
        "baseline_verdict": baseline_verdict,
        "baseline_penalty_or_boost": _round(baseline_penalty_or_boost),
        "baseline_source": baseline_source,
        "baseline_reason": baseline_reason,
        "status_cap": _round(_STATUS_CAP.get(status, 0.30)),
        "expectancy_reason_source": reason_source,
        "fallback_candidate": fallback_candidate,
            "feed_blocked": feed_blocked,
            "edge_rank_score": _round(edge_rank_score),
        }
    )
    row["edge_rank_score"] = _round(edge_rank_score)
    row["edge_rank_reason"] = _build_reason(
        status=status,
        capped=capped,
        fallback_candidate=fallback_candidate,
        feed_blocked=feed_blocked,
        regime_mismatch_reasons=list(components.get("candidate_regime_mismatch_reasons") or []),
        crowding_reasons=list(components.get("crowding_reasons") or []),
    )
    if baseline_verdict in {"OUTPERFORMS", "MATCHES", "UNDERPERFORMS"}:
        row["edge_rank_reason"] = "|".join([row["edge_rank_reason"], f"baseline={baseline_verdict}"])
    row["edge_rank_components"] = components
    row["expectancy_score"] = components["expectancy_score"]
    row["expectancy_status"] = status
    row["expectancy_sample_count"] = sample_count
    row["expectancy_avg_cost_adjusted_r"] = _round(avg_cost_adjusted_r)
    row["baseline_verdict"] = baseline_verdict
    row["baseline_penalty_or_boost"] = _round(baseline_penalty_or_boost)
    row["baseline_source"] = baseline_source
    row["baseline_reason"] = baseline_reason
    return row


__all__ = [
    "EDGE_RANK_SCHEMA_VERSION",
    "EdgeRankDecision",
    "apply_edge_ranking",
]
