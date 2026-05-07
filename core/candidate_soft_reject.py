from __future__ import annotations

from datetime import datetime, timezone
from datetime import date as _date
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable

from config import config as cfg


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _lower_text(value: Any) -> str:
    return _normalize_text(value).lower()


def _normalize_instrument_type(value: Any) -> str:
    text = _normalize_text(value).upper()
    if not text:
        return ""
    if text in {"OPT", "OPTION", "OPTIONS", "OPTIDX", "OPTSTK", "CE", "PE", "CALL", "PUT"}:
        return "OPT"
    if text in {"EQ", "STK", "STOCK"}:
        return "EQ"
    if text in {"FUT", "FUTURE", "FUTURES"}:
        return "FUT"
    if text in {"INDEX", "IDX"}:
        return "INDEX"
    return text


def _assume_opt_candidate_types() -> set[str]:
    raw = _normalize_text(getattr(cfg, "ADVISORY_INSTRUMENT_TYPE_ASSUME_OPT_CANDIDATE_TYPES", ""))
    if not raw:
        return set()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _instrument_type_fallback() -> str:
    fallback = _normalize_text(getattr(cfg, "ADVISORY_INSTRUMENT_TYPE_FALLBACK", "UNKNOWN"))
    return fallback.upper() if fallback else "UNKNOWN"


def _infer_option_type(payload: dict[str, Any], market_data: dict[str, Any]) -> tuple[str | None, str]:
    explicit = _normalize_text(payload.get("option_type") or payload.get("type") or payload.get("right")).upper()
    if explicit in {"CE", "PE"}:
        return explicit, "explicit"
    trend = _normalize_text(payload.get("trend") or market_data.get("trend") or "").lower()
    if trend in {"bullish", "uptrend"}:
        return "CE", "trend"
    if trend in {"bearish", "downtrend"}:
        return "PE", "trend"
    direction = _normalize_text(payload.get("direction") or "").upper()
    if "PUT" in direction or direction.endswith("PE"):
        return "PE", "direction"
    if "CALL" in direction or direction.endswith("CE"):
        return "CE", "direction"
    fallback = _normalize_text(getattr(cfg, "ADVISORY_OPTION_TYPE_FALLBACK", "CE")).upper()
    return (fallback or None), "fallback" if fallback else "none"


def _infer_direction(option_type: str | None) -> str | None:
    if option_type == "CE":
        return "BUY_CALL"
    if option_type == "PE":
        return "BUY_PUT"
    return None


def _infer_strategy_family(payload: dict[str, Any], market_data: dict[str, Any]) -> str:
    explicit = _normalize_text(
        payload.get("strategy_family")
        or payload.get("strategy")
        or market_data.get("strategy_family")
        or market_data.get("strategy")
    )
    if explicit:
        return explicit
    fallback = _normalize_text(getattr(cfg, "SOFT_REJECT_STRATEGY_FAMILY_FALLBACK", "breakout"))
    return fallback or "breakout"


def _parse_expiry(value: Any) -> _date | None:
    if value is None or value == "":
        return None
    if isinstance(value, _date):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).date()
        except Exception:
            return None
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        pass
    try:
        return datetime.strptime(text.split("T")[0], "%Y-%m-%d").date()
    except Exception:
        return None


def _infer_instrument_type(payload: dict[str, Any], market_data: dict[str, Any]) -> tuple[str, str]:
    explicit = _normalize_instrument_type(
        payload.get("instrument_type")
        or payload.get("instrument")
        or market_data.get("instrument_type")
        or market_data.get("instrument")
    )
    if explicit:
        return explicit, "explicit"
    option_type = _normalize_text(
        payload.get("option_type")
        or payload.get("type")
        or payload.get("right")
        or market_data.get("option_type")
        or market_data.get("right")
    ).upper()
    if option_type in {"CE", "PE", "CALL", "PUT"}:
        return "OPT", "option_type"
    symbol_hint = _normalize_text(payload.get("tradingsymbol") or payload.get("instrument_id") or "")
    if symbol_hint.endswith("CE") or symbol_hint.endswith("PE"):
        return "OPT", "symbol_suffix"
    candidate_type = _lower_text(payload.get("candidate_type"))
    if candidate_type and candidate_type in _assume_opt_candidate_types():
        return "OPT", "candidate_type"
    return _instrument_type_fallback(), "fallback"


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _coerce_reason_list(reasons: Iterable[Any]) -> list[str]:
    cleaned: list[str] = []
    for reason in reasons:
        text = _normalize_text(reason)
        if text:
            cleaned.append(text)
    return cleaned


def soft_reject_enabled(execution_mode: str | None) -> bool:
    try:
        enabled = bool(getattr(cfg, "CANDIDATE_SOFT_REJECT_ENABLE", True))
    except Exception:
        enabled = False
    if not enabled:
        return False
    try:
        allow_live = bool(getattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_LIVE", False))
    except Exception:
        allow_live = False
    mode = _normalize_text(execution_mode).upper()
    if mode in {"LIVE", "REAL"} and not allow_live:
        return False
    return True


def soft_reject_max_per_symbol() -> int:
    try:
        return max(int(getattr(cfg, "CANDIDATE_SOFT_REJECT_MAX_PER_SYMBOL", 3)), 1)
    except Exception:
        return 1


def soft_reject_confidence() -> float:
    try:
        return float(getattr(cfg, "CANDIDATE_SOFT_REJECT_CONFIDENCE", 0.1))
    except Exception:
        return 0.1


def critical_reject_reasons() -> set[str]:
    raw = _normalize_text(getattr(cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", ""))
    if not raw:
        return set()
    reasons = {item.strip().lower() for item in raw.split(",") if item.strip()}
    allow_unknown = bool(getattr(cfg, "CANDIDATE_SOFT_REJECT_ALLOW_UNKNOWN_CRITICAL", False))
    if not allow_unknown:
        # Never treat fallback unknown as critical unless explicitly configured.
        reasons.discard("unknown_reject")
    return reasons


def is_critical_reject_reason(reason: str, critical: set[str] | None = None) -> bool:
    text = _normalize_text(reason).lower()
    if not text:
        return False
    if critical is None:
        critical = critical_reject_reasons()
    if text == "unknown_reject" and text not in critical:
        return False
    return text in critical


def _unknown_reject_confidence() -> float:
    try:
        return float(getattr(cfg, "CANDIDATE_SOFT_REJECT_UNKNOWN_CONFIDENCE", 0.08))
    except Exception:
        return 0.08


def _soft_reject_confidence_min() -> float:
    try:
        return float(getattr(cfg, "CANDIDATE_SOFT_REJECT_CONF_MIN", 0.05))
    except Exception:
        return 0.05


def _soft_reject_penalties(reasons: list[str]) -> float:
    penalty = 0.0
    prem = float(getattr(cfg, "CANDIDATE_SOFT_REJECT_PENALTY_PREMIUM", 0.05))
    spread = float(getattr(cfg, "CANDIDATE_SOFT_REJECT_PENALTY_SPREAD", 0.07))
    latency = float(getattr(cfg, "CANDIDATE_SOFT_REJECT_PENALTY_LATENCY", 0.1))
    for reason in reasons:
        text = _normalize_text(reason).lower()
        if "premium" in text:
            penalty += prem
        if "spread" in text:
            penalty += spread
        if "latency" in text or "stale" in text:
            penalty += latency
    return penalty


def _compute_soft_reject_confidence(reject_reason: str, penalties: list[str]) -> float:
    base = soft_reject_confidence()
    if _normalize_text(reject_reason).lower() == "unknown_reject":
        base = _unknown_reject_confidence()
    score = base - _soft_reject_penalties(penalties)
    score = min(1.0, max(_soft_reject_confidence_min(), score))
    return score


def _soft_reject_status_from_confidence(candidate: dict[str, Any]) -> tuple[str, str]:
    confidence = 0.0
    try:
        confidence = max(
            float(candidate.get("confidence", 0.0) or 0.0),
            float(candidate.get("rank_score", 0.0) or 0.0),
            float(candidate.get("confidence_final", 0.0) or 0.0),
        )
    except Exception:
        confidence = 0.0
    borderline_floor = float(getattr(cfg, "TRADE_BUILDER_BORDERLINE_CONF_MIN", 0.18) or 0.18)
    if confidence >= borderline_floor:
        return "scored", "soft_reject_but_salvageable"
    return "advisory_only", "soft_reject_low_confidence"


def _recoverable_soft_reject_reasons() -> set[str]:
    raw = _normalize_text(
        getattr(
            cfg,
            "CANDIDATE_SOFT_REJECT_RECOVERABLE_REASONS",
            "no_signal,weak_signal,no_candidates_survived,latency_guard_cooldown,regime_unstable",
        )
    )
    if not raw:
        return {"no_signal", "weak_signal", "no_candidates_survived", "latency_guard_cooldown", "regime_unstable"}
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _is_recoverable_soft_reject(reason: str) -> bool:
    return _lower_text(reason) in _recoverable_soft_reject_reasons()


def build_soft_reject_candidate(
    market_data: dict[str, Any] | None,
    *,
    reject_reason: str,
    reject_source: str,
    gate_reasons: Iterable[Any] | None = None,
    base_candidate: dict[str, Any] | None = None,
    execution_mode: str | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = dict(base_candidate or {})
    market_data = market_data or {}
    symbol = _normalize_text(payload.get("symbol") or market_data.get("symbol") or market_data.get("underlying"))
    if not symbol:
        return None
    ts_epoch = _now_epoch()
    penalties = _coerce_reason_list(gate_reasons or []) or _coerce_reason_list([reject_reason])
    reject_text = _lower_text(reject_reason)
    confidence = _compute_soft_reject_confidence(reject_reason, penalties)
    reject_source_label = _normalize_text(reject_source)
    if reject_text == "unknown_reject":
        reject_source_label = "fallback_unknown"
    recoverable = _is_recoverable_soft_reject(reject_reason)

    if recoverable:
        candidate_status = "near_executable"
        final_action = "QUEUE_ONLY"
        permission = "QUEUE_ONLY"
        readiness_state = "QUEUE_ONLY"
        execution_status = "scored"
        execution_entry = payload.get("execution_entry")
        execution_entry_source = _normalize_text(payload.get("execution_entry_source")) or "soft_reject_recovery"
        execution_entry_status = _normalize_text(payload.get("execution_entry_status")) or "pending"
        display_entry = payload.get("display_entry")
        display_entry_source = _normalize_text(payload.get("display_entry_source")) or "soft_reject_recovery"
        display_entry_status = _normalize_text(payload.get("display_entry_status")) or "pending"
        entry = payload.get("entry")
        entry_source = _normalize_text(payload.get("entry_source")) or "soft_reject_recovery"
        entry_status = _normalize_text(payload.get("entry_status")) or "pending"
        execution_blocked = False
        execution_block_reason = None
        eligible_for_execution = True
        execution_allowed = True
        execution_ok = True
        row_kind = "queue_only"
        candidate_origin = "softened_builder_path"
        candidate_class = "softened"
        trade_id = _normalize_text(payload.get("trade_id")) or f"tbsoft_{symbol}_{int(ts_epoch * 1000)}"
    else:
        candidate_status = "advisory_only"
        final_action = "ADVISORY_ONLY"
        permission = "ADVISORY_ONLY"
        readiness_state = "ADVISORY_ONLY"
        execution_status = "advisory_only"
        execution_entry = None
        execution_entry_source = "none"
        execution_entry_status = "non_executable"
        display_entry = None
        display_entry_source = "none"
        display_entry_status = "missing"
        entry = None
        entry_source = "none"
        entry_status = "missing"
        execution_blocked = True
        execution_block_reason = _normalize_text(reject_reason) or "soft_reject"
        eligible_for_execution = False
        execution_allowed = False
        execution_ok = False
        row_kind = "advisory_only"
        candidate_origin = _normalize_text(payload.get("candidate_origin")) or "synthetic_advisory"
        candidate_class = "synthetic"
        trade_id = _normalize_text(payload.get("trade_id")) or f"softrej_{symbol}_{int(ts_epoch * 1000)}"

    payload.update(
        {
            "trade_id": trade_id,
            "symbol": symbol,
            "tradingsymbol": _normalize_text(payload.get("tradingsymbol")) or symbol,
            "candidate_type": _normalize_text(payload.get("candidate_type")) or ("directional" if recoverable else "unknown"),
            "strategy_family": _normalize_text(payload.get("strategy_family")) or ("builder_soft_reject" if recoverable else "synthetic_advisory"),
            "setup_variant": _normalize_text(payload.get("setup_variant")) or ("softened_builder_path" if recoverable else "unknown"),
            "direction": _normalize_text(payload.get("direction")) or "UNKNOWN",
            "candidate_origin": candidate_origin,
            "candidate_class": candidate_class,
            "candidate_status": candidate_status,
            "advisory_visible": True,
            "final_action": final_action,
            "permission": permission,
            "readiness": readiness_state,
            "execution_status": execution_status,
            "execution_entry": execution_entry,
            "execution_entry_source": execution_entry_source,
            "execution_entry_status": execution_entry_status,
            "display_entry": display_entry,
            "display_entry_source": display_entry_source,
            "display_entry_status": display_entry_status,
            "entry": entry,
            "entry_source": entry_source,
            "entry_status": entry_status,
            "entry_clear_reason": _lower_text(reject_reason) or "soft_reject",
            "entry_block_code": _lower_text(reject_reason) or "soft_reject",
            "soft_penalties": penalties,
            "warnings": list(payload.get("warnings") or []),
            "hard_blockers": list(payload.get("hard_blockers") or []),
            "reject_reason": _normalize_text(reject_reason),
            "reject_source": reject_source_label,
            "reject_reason_source": reject_source_label,
            "gate_reasons": penalties,
            "execution_blocked": execution_blocked,
            "execution_block_reason": execution_block_reason,
            "eligible_for_execution": eligible_for_execution,
            "execution_allowed": execution_allowed,
            "execution_ok": execution_ok,
            "confidence_raw": confidence,
            "confidence_penalty": 0.0,
            "confidence_final": confidence,
            "confidence": confidence,
            "soft_reject_seed_confidence": confidence,
            "rank_score": (
                _safe_float(payload.get("rank_score"))
                if _safe_float(payload.get("rank_score")) is not None
                else (None if recoverable else confidence)
            ),
            "opportunity_score": (
                _safe_float(payload.get("opportunity_score"))
                if _safe_float(payload.get("opportunity_score")) is not None
                else (None if recoverable else confidence)
            ),
            "ts_epoch": float(payload.get("ts_epoch") or ts_epoch),
            "timestamp": payload.get("timestamp") or datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat(),
            "row_kind": row_kind,
        }
    )
    if recoverable:
        existing_family = _normalize_text(
            (base_candidate or {}).get("strategy_family") if isinstance(base_candidate, dict) else payload.get("strategy_family")
        )
        if existing_family and existing_family.lower() != "synthetic_advisory":
            payload["strategy_family"] = existing_family
        elif _normalize_text(payload.get("strategy_family")).lower() in {"", "unknown", "synthetic_advisory"}:
            payload["strategy_family"] = "builder_soft_reject"
    source_flags = dict(payload.get("source_flags") or {})
    source_flags["candidate_origin"] = candidate_origin
    source_flags["soft_reject_reason"] = _normalize_text(reject_reason)
    source_flags["recoverable_soft_reject"] = bool(recoverable)
    payload["source_flags"] = source_flags
    option_type, option_source = _infer_option_type(payload, market_data)
    if option_type:
        payload["option_type"] = option_type
        payload.setdefault("option_type_source", option_source)
    inferred_direction = _infer_direction(option_type)
    if inferred_direction and not _normalize_text(payload.get("direction")):
        payload["direction"] = inferred_direction
    instrument_type, instrument_source = _infer_instrument_type(payload, market_data)
    if instrument_type:
        payload["instrument_type"] = instrument_type
        payload.setdefault("instrument_type_source", instrument_source)
        if instrument_source == "fallback":
            payload.setdefault("failure_reason", "instrument_type_backfilled")
    hide_unknown = bool(getattr(cfg, "ADVISORY_HIDE_UNKNOWN_INSTRUMENT", True))
    if hide_unknown and instrument_type == "UNKNOWN":
        payload["advisory_visible"] = False
    payload["execution_mode"] = _normalize_text(payload.get("execution_mode")) or _normalize_text(execution_mode)
    return payload


def apply_latency_penalty(
    candidate: dict[str, Any],
    *,
    latency_action: str | None,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    if isinstance(candidate, dict):
        out = dict(candidate)
    elif is_dataclass(candidate):
        out = asdict(candidate)
    elif hasattr(candidate, "__dict__"):
        out = dict(vars(candidate))
    else:
        return {}
    action = _normalize_text(latency_action).lower()
    penalty = _safe_float(getattr(cfg, "LATENCY_SOFT_PENALTY", 0.25)) or 0.0
    min_conf = _soft_reject_confidence_min()

    def _penalize(value: float | None) -> float | None:
        if value is None:
            return None
        if penalty <= 0:
            return value
        if penalty >= 1:
            return max(min_conf, value - penalty)
        return max(min_conf, value * max(0.0, 1.0 - penalty))

    confidence_before = _safe_float(out.get("confidence_final"))
    if confidence_before is None:
        confidence_before = _safe_float(out.get("confidence"))

    confidence_after = _penalize(confidence_before)
    if confidence_after is not None:
        out["confidence"] = confidence_after
        out["confidence_final"] = confidence_after

    rank_before = _safe_float(out.get("rank_score"))
    rank_after = _penalize(rank_before)
    if rank_after is not None:
        out["rank_score"] = rank_after

    opp_before = _safe_float(out.get("opportunity_score"))
    opp_after = _penalize(opp_before)
    if opp_after is not None:
        out["opportunity_score"] = opp_after

    warnings = list(out.get("warnings") or [])
    warning_code = f"latency_guard_{action}" if action else "latency_guard"
    if warning_code not in warnings:
        warnings.append(warning_code)
    out["warnings"] = warnings

    soft_penalties = list(out.get("soft_penalties") or [])
    if warning_code not in soft_penalties:
        soft_penalties.append(warning_code)
    out["soft_penalties"] = soft_penalties

    execution_blockers = list(out.get("execution_blockers") or out.get("blockers") or [])
    if warning_code not in execution_blockers:
        execution_blockers.append(warning_code)
    out["execution_blockers"] = execution_blockers

    out["latency_softened"] = True
    out["latency_guard_action"] = action or "unknown"
    was_executable = str(out.get("execution_status") or "").lower() == "executable" or bool(
        out.get("execution_allowed")
    )
    soft_status, subreason = _soft_reject_status_from_confidence(
        {
            "confidence": confidence_after,
            "rank_score": rank_after,
            "confidence_final": confidence_after,
        }
    )
    recoverable_queue_only = bool(soft_status == "scored")
    out["execution_allowed"] = False
    out["execution_ok"] = False
    out["execution_status"] = "queue_only" if recoverable_queue_only else "advisory_only"
    out["order_policy"] = "reject"
    out["order_policy_reason"] = warning_code
    out["execution_blocked"] = True
    out["execution_block_reason"] = warning_code
    if was_executable:
        out["candidate_status"] = "near_executable"
    else:
        out.setdefault("candidate_status", "near_executable" if recoverable_queue_only else "advisory_only")
    out["eligible_for_execution"] = False
    out["permission"] = "QUEUE_ONLY" if recoverable_queue_only else "ADVISORY_ONLY"
    out["final_action"] = "QUEUE_ONLY" if recoverable_queue_only else "ADVISORY_ONLY"
    out["readiness"] = "QUEUE_ONLY" if recoverable_queue_only else "ADVISORY_ONLY"

    out["row_kind"] = "queue_only" if recoverable_queue_only else "advisory_only"
    preserve_strategy = bool(getattr(cfg, "LATENCY_SOFTEN_PRESERVE_STRATEGY_FAMILY", True))
    if not preserve_strategy and not out.get("strategy_family"):
        out["strategy_family"] = "unknown"
    if not out.get("option_type"):
        opt_type, _src = _infer_option_type(out, {})
        if opt_type:
            out["option_type"] = opt_type
    if not out.get("direction"):
        direction = _infer_direction(_normalize_text(out.get("option_type")).upper())
        if direction:
            out["direction"] = direction
    if not out.get("instrument_type"):
        inst, _inst_src = _infer_instrument_type(out, {})
        out["instrument_type"] = inst

    return out


def build_min_breadth_candidate(
    market_data: dict[str, Any] | None,
    *,
    execution_mode: str | None,
    seed_candidate: dict[str, Any] | None = None,
    reason: str = "min_candidate_backfill",
) -> dict[str, Any] | None:
    market_data = market_data or {}
    base = dict(seed_candidate or {})
    if "symbol" not in base:
        base["symbol"] = market_data.get("symbol") or market_data.get("underlying")
    if "candidate_type" not in base:
        base["candidate_type"] = "directional"
    if "strategy_family" not in base or not base.get("strategy_family"):
        base["strategy_family"] = _infer_strategy_family(base, market_data)
    if not base.get("option_type"):
        opt_type, _src = _infer_option_type(base, market_data)
        if opt_type:
            base["option_type"] = opt_type
    if not base.get("direction"):
        direction = _infer_direction(_normalize_text(base.get("option_type")).upper())
        if direction:
            base["direction"] = direction
    if not base.get("instrument_type"):
        inst, _src = _infer_instrument_type(base, market_data)
        base["instrument_type"] = inst

    candidate = build_soft_reject_candidate(
        market_data,
        reject_reason=reason,
        reject_source="orchestrator_min_breadth",
        gate_reasons=[reason],
        base_candidate=base,
        execution_mode=execution_mode,
    )
    if not candidate:
        return None
    candidate["candidate_origin"] = "fallback_min_breadth"
    source_flags = dict(candidate.get("source_flags") or {})
    source_flags["candidate_origin"] = "fallback_min_breadth"
    candidate["source_flags"] = source_flags
    candidate["execution_allowed"] = False
    candidate["execution_ok"] = False
    candidate["execution_status"] = "advisory_only"
    candidate["candidate_status"] = "advisory_only"
    candidate["row_kind"] = "advisory_only"
    fallback_conf = _safe_float(getattr(cfg, "MIN_BREADTH_FALLBACK_CONFIDENCE", None))
    if fallback_conf is not None:
        candidate["confidence"] = fallback_conf
        candidate["confidence_final"] = fallback_conf
        candidate["rank_score"] = fallback_conf
    return candidate


def build_min_breadth_candidates(
    market_data: dict[str, Any] | None,
    *,
    execution_mode: str | None,
    seed_candidate: dict[str, Any] | None = None,
    min_needed: int = 1,
) -> list[dict[str, Any]]:
    market_data = market_data or {}
    chain_rows = list(market_data.get("option_chain") or [])
    max_per_symbol = int(getattr(cfg, "MIN_BREADTH_FALLBACK_MAX_PER_SYMBOL", 4))
    if max_per_symbol <= 0:
        max_per_symbol = 1
    use_nearest_strikes = bool(getattr(cfg, "MIN_BREADTH_USE_NEAREST_STRIKES", True))
    infer_direction = bool(getattr(cfg, "MIN_BREADTH_DIRECTION_INFERENCE_ENABLE", True))
    fallback_conf = _safe_float(getattr(cfg, "MIN_BREADTH_FALLBACK_CONFIDENCE", 0.12)) or 0.12

    spot = _safe_float(
        market_data.get("underlying_spot")
        or market_data.get("spot")
        or market_data.get("ltp")
        or market_data.get("current_ltp")
    )

    expiry_rows: list[dict[str, Any]] = []
    if chain_rows:
        expiry_map: dict[_date, list[dict[str, Any]]] = {}
        for row in chain_rows:
            exp = _parse_expiry(row.get("expiry_date") or row.get("expiry"))
            if exp is None:
                continue
            expiry_map.setdefault(exp, []).append(row)
        if expiry_map:
            nearest = sorted(expiry_map.keys())[0]
            expiry_rows = expiry_map.get(nearest, [])

    rows = expiry_rows or chain_rows
    strikes = sorted(
        {
            _safe_float(row.get("strike"))
            for row in rows
            if _safe_float(row.get("strike")) is not None
        }
    )
    strikes = [s for s in strikes if s is not None]
    atm = None
    if strikes and spot is not None:
        atm = min(strikes, key=lambda s: abs(float(s) - float(spot)))
    elif strikes:
        atm = strikes[len(strikes) // 2]

    step = None
    if len(strikes) >= 2:
        deltas = [abs(strikes[i + 1] - strikes[i]) for i in range(len(strikes) - 1)]
        deltas = [d for d in deltas if d > 0]
        if deltas:
            step = min(deltas)

    target_strikes: list[float] = []
    if atm is not None:
        target_strikes.append(float(atm))
        if use_nearest_strikes and step:
            target_strikes.extend([float(atm - step), float(atm + step)])

    direction = _normalize_text(market_data.get("trend") or market_data.get("direction") or "").lower()
    option_types: list[str] = []
    if infer_direction and direction in {"bullish", "uptrend"}:
        option_types = ["CE"]
    elif infer_direction and direction in {"bearish", "downtrend"}:
        option_types = ["PE"]
    else:
        option_types = ["CE", "PE"]

    candidates: list[dict[str, Any]] = []
    for strike in target_strikes or [None]:
        for opt_type in option_types:
            match = None
            for row in rows:
                if _safe_float(row.get("strike")) == _safe_float(strike) and str(
                    row.get("type") or row.get("option_type") or ""
                ).upper() == opt_type:
                    match = row
                    break
            base = dict(seed_candidate or {})
            base.update(
                {
                    "symbol": market_data.get("symbol") or market_data.get("underlying"),
                    "candidate_type": "fallback_market_candidate",
                    "strategy_family": "fallback_breadth",
                    "option_type": opt_type,
                    "direction": _infer_direction(opt_type) or base.get("direction"),
                    "instrument_type": "OPT",
                    "strike": strike,
                }
            )
            if match:
                base["tradingsymbol"] = match.get("tradingsymbol") or base.get("tradingsymbol")
                base["instrument_token"] = match.get("instrument_token") or base.get("instrument_token")
                base["expiry"] = match.get("expiry") or match.get("expiry_date") or base.get("expiry")
                base["expiry_date"] = match.get("expiry_date") or base.get("expiry_date")

            candidate = build_soft_reject_candidate(
                market_data,
                reject_reason="min_candidate_backfill",
                reject_source="orchestrator_min_breadth",
                gate_reasons=["min_candidate_backfill"],
                base_candidate=base,
                execution_mode=execution_mode,
            )
            if candidate:
                candidate["candidate_origin"] = "fallback_min_breadth"
                source_flags = dict(candidate.get("source_flags") or {})
                source_flags["candidate_origin"] = "fallback_min_breadth"
                source_flags["fallback_min_breadth"] = True
                candidate["source_flags"] = source_flags
                candidate["execution_allowed"] = False
                candidate["execution_ok"] = False
                candidate["execution_status"] = "advisory_only"
                candidate["candidate_status"] = "advisory_only"
                candidate["row_kind"] = "advisory_only"
                candidate["rank_score"] = fallback_conf
                candidate["confidence"] = fallback_conf
                candidate["confidence_final"] = fallback_conf
                candidates.append(candidate)
                if len(candidates) >= max(min_needed, 1):
                    break
        if len(candidates) >= max(min_needed, 1):
            break

    if len(candidates) > max_per_symbol:
        candidates = candidates[:max_per_symbol]
    return candidates
