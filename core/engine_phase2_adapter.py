from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import logging
import time
from typing import Any

from config import config as cfg
from core.trade_scoring import compute_final_score

logger = logging.getLogger("phase2")


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _safe_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _mode_for_candidate(candidate: dict[str, Any] | None = None) -> str:
    if isinstance(candidate, dict):
        text = str(
            candidate.get("execution_mode")
            or candidate.get("market_mode")
            or candidate.get("mode")
            or ""
        ).strip().upper()
        if text:
            return text
    return str(getattr(cfg, "EXECUTION_MODE", "SIM") or "SIM").strip().upper()


def _allow_relaxed_live() -> bool:
    return bool(getattr(cfg, "PHASE2_RELAX_ALLOW_LIVE", False))


def _live_mode(mode: str) -> bool:
    return str(mode or "").strip().upper() in {"LIVE", "REAL"}


def safe_get(c: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(c.get(key, default))
    except Exception:
        return default


def _candidate_to_dict(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return dict(candidate)
    if is_dataclass(candidate):
        return asdict(candidate)
    out: dict[str, Any] = {}
    for key in dir(candidate):
        if key.startswith("_"):
            continue
        try:
            value = getattr(candidate, key)
        except Exception:
            continue
        if callable(value):
            continue
        out[key] = value
    return out


def validate_candidate(c: dict[str, Any]) -> bool:
    required_keys = ["symbol"]
    for key in required_keys:
        if key not in c or c[key] in [None, ""]:
            return False
    return True


def _candidate_hour(candidate: dict[str, Any]) -> int:
    epoch = (
        _safe_float(candidate.get("timestamp_epoch"))
        or _safe_float(candidate.get("decision_ts_epoch"))
        or _safe_float(candidate.get("ts_epoch"))
    )
    if epoch is not None and epoch > 0:
        try:
            return int(datetime.fromtimestamp(float(epoch)).hour)
        except Exception:
            pass
    return int(datetime.now().hour)


def _spread_pct(candidate: dict[str, Any]) -> float | None:
    spread_pct = _safe_float(candidate.get("spread_pct"))
    if spread_pct is not None:
        return max(0.0, spread_pct)
    bid = _safe_float(candidate.get("best_bid"))
    ask = _safe_float(candidate.get("best_ask"))
    ltp = _safe_float(candidate.get("opt_ltp")) or _safe_float(candidate.get("current_ltp"))
    if bid is None or ask is None or ltp in (None, 0.0):
        return None
    return max(0.0, float(ask - bid) / max(float(ltp), 1e-9))


def _liquidity_score(candidate: dict[str, Any]) -> float:
    score = _safe_float(candidate.get("liquidity_score"))
    if score is not None:
        return max(0.0, min(1.0, score))
    liquidity_ok = candidate.get("liquidity_ok")
    if liquidity_ok is not None:
        return 1.0 if _safe_bool(liquidity_ok, default=False) else 0.0
    volume = _safe_float(candidate.get("volume")) or _safe_float(candidate.get("current_volume")) or 0.0
    min_volume = max(float(getattr(cfg, "MIN_VOLUME_FILTER", 1.0) or 1.0), 1.0)
    return max(0.0, min(1.0, float(volume) / min_volume))


def _execution_quality_score(candidate: dict[str, Any]) -> float:
    for key in (
        "execution_quality_score",
        "execution_score",
        "fill_probability",
        "selection_probability",
    ):
        value = _safe_float(candidate.get(key))
        if value is not None:
            return max(0.0, min(1.0, value))
    execution_allowed = _safe_bool(candidate.get("execution_allowed"), default=True)
    tradable = _safe_bool(candidate.get("tradable"), default=True)
    return 1.0 if (execution_allowed and tradable) else 0.0


def _reason_codes(candidate: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("reject_reason", "reason", "execution_block_reason"):
        text = str(candidate.get(key) or "").strip()
        if text:
            out.append(text.upper())
    for key in ("gate_reasons", "blockers", "hard_blockers", "execution_blockers"):
        for value in list(candidate.get(key) or []):
            text = str(value or "").strip()
            if text:
                out.append(text.upper())
    return out


def _is_no_signal_candidate(candidate: dict[str, Any]) -> bool:
    return any("NO_SIGNAL" in code for code in _reason_codes(candidate))


def _is_latency_only_block(candidate: dict[str, Any]) -> bool:
    codes = _reason_codes(candidate)
    if not codes:
        return False
    has_latency = any("LATENCY_GUARD" in code or "LATENCY" in code for code in codes)
    if not has_latency:
        return False
    disallowed = {
        "FEED_STALE",
        "NO_LIVE_OPTION_FEED",
        "UNRESOLVED_CONTRACT",
        "MISSING_CONTRACT_FIELDS",
        "MISSING_OPTION_TOKEN",
        "NO_TOKEN",
    }
    return not any(code in disallowed for code in codes)


def _is_borderline_execution_candidate(candidate: dict[str, Any]) -> bool:
    candidate_status = str(candidate.get("candidate_status") or "").strip().lower()
    execution_status = str(candidate.get("execution_status") or "").strip().lower()
    candidate_origin = str(candidate.get("candidate_origin") or "").strip().lower()
    if candidate_status in {"near_executable", "queue_only", "scored"}:
        return True
    if execution_status in {"queue_only", "scored"}:
        return True
    if "softened_builder_path" in candidate_origin:
        return True
    return bool(candidate.get("soft_blockers"))


def _hard_filter_reasons(candidate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    soft_penalties: list[str] = list(candidate.get("phase2_soft_penalties") or [])
    mode = _mode_for_candidate(candidate)
    allow_relax = not _live_mode(mode) or _allow_relaxed_live()
    no_signal_relax = bool(getattr(cfg, "PHASE2_RELAX_NO_SIGNAL", True)) and allow_relax
    latency_relax = bool(getattr(cfg, "PHASE2_DISABLE_LATENCY_BLOCK", True)) and allow_relax

    base_spread = float(
        getattr(cfg, "PHASE2_MAX_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.02))
        or getattr(cfg, "MAX_SPREAD_PCT", 0.02)
    )
    high_vol_spread = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", 0.02) or 0.02)
    vol_cutoff = float(getattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
    volatility = max(
        safe_get(candidate, "volatility", 0.0),
        safe_get(candidate, "volatility_score", 0.0),
        safe_get(candidate, "vol_z", 0.0),
    )
    max_spread = high_vol_spread if volatility > vol_cutoff else base_spread
    market_start_hour = int(getattr(cfg, "PHASE2_MARKET_START_HOUR", 9) or 9)
    market_end_hour = int(getattr(cfg, "PHASE2_MARKET_END_HOUR", 15) or 15)
    offhours_mult = float(getattr(cfg, "PHASE2_SPREAD_OFFHOURS_MULT", 1.5) or 1.5)
    hour = _candidate_hour(candidate)
    if hour < market_start_hour or hour > market_end_hour:
        max_spread *= offhours_mult
    spread_pct = _spread_pct(candidate)
    if spread_pct is not None and spread_pct >= max_spread:
        reasons.append("hard_spread")

    execution_allowed = _safe_bool(candidate.get("execution_allowed"), default=True)
    tradable = _safe_bool(candidate.get("tradable"), default=True)
    execution_ok = candidate.get("execution_ok")
    execution_blocked = _safe_bool(candidate.get("execution_blocked"), default=False)
    min_execution_score = float(getattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.50) or 0.50)
    execution_score = _execution_quality_score(candidate)
    no_signal_candidate = _is_no_signal_candidate(candidate)
    latency_only_block = _is_latency_only_block(candidate)
    if no_signal_relax and no_signal_candidate:
        execution_allowed = True
        tradable = True
        if execution_ok is False:
            execution_ok = True
    if latency_relax and latency_only_block:
        execution_blocked = False
        if execution_ok is False:
            execution_ok = True
    if (
        (not execution_allowed)
        or (not tradable)
        or execution_blocked
        or execution_ok is False
        or execution_score < min_execution_score
    ):
        reasons.append("hard_execution")

    min_liq_score = float(getattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.35) or 0.35)
    liquidity_score = _liquidity_score(candidate)
    if liquidity_score < min_liq_score:
        if _is_borderline_execution_candidate(candidate):
            soft_penalties.append("liquidity_penalty")
            candidate["phase2_liquidity_penalty"] = float(min_liq_score - liquidity_score)
        else:
            reasons.append("hard_liquidity")

    candidate["phase2_soft_penalties"] = soft_penalties

    return reasons


def _compute_phase2_final_score(candidate: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    existing = _safe_float(candidate.get("final_score"))
    if existing is not None:
        return float(existing), {}

    market_mode = str(
        candidate.get("market_mode")
        or candidate.get("execution_mode")
        or getattr(cfg, "EXECUTION_MODE", "SIM")
    ).strip().upper()
    candidate_class = str(candidate.get("candidate_class") or "").strip().upper()
    if not candidate_class:
        if _safe_bool(candidate.get("execution_allowed"), True) and _safe_bool(candidate.get("tradable"), True):
            candidate_class = "EXECUTABLE"
        else:
            candidate_class = "ADVISORY_ONLY"

    signal_score = safe_get(candidate, "signal_score", 0.0)
    execution_score = safe_get(candidate, "execution_score", 0.0)
    liquidity_score = safe_get(candidate, "liquidity_score", 0.0)

    setup_score = _safe_float(candidate.get("setup_score"))
    trigger_score = _safe_float(candidate.get("trigger_score"))
    entry_quality_score = _safe_float(candidate.get("entry_quality_score"))
    family_survival_score = _safe_float(candidate.get("family_survival_score"))
    setup_quality = setup_score
    if setup_quality is None:
        setup_quality = signal_score
    if setup_quality is None:
        setup_quality = _safe_float(candidate.get("trade_score"))
        if setup_quality is not None and setup_quality > 1.0:
            setup_quality = max(0.0, min(1.0, setup_quality / 100.0))
    confluence_score = (
        _safe_float(candidate.get("confidence_final"))
        or _safe_float(candidate.get("gating_final_confidence"))
        or _safe_float(candidate.get("confidence"))
        or _safe_float(candidate.get("signal_score"))
        or 0.0
    )
    regime_fit = (
        _safe_float(candidate.get("regime_fit"))
        or _safe_float(candidate.get("regime_score"))
        or _safe_float(candidate.get("trade_alignment"))
        or 0.5
    )

    result = compute_final_score(
        candidate,
        candidate_class=candidate_class,
        market_mode=market_mode or "SIM",
        setup_quality=setup_quality,
        confluence_score=confluence_score,
        regime_fit=regime_fit,
        liquidity_quality=max(_liquidity_score(candidate), liquidity_score),
        freshness_quality=(
            _safe_float(candidate.get("freshness_quality"))
            or (1.0 if _safe_bool(candidate.get("fresh_quote_ok"), default=True) else 0.0)
        ),
        execution_feasibility=max(_execution_quality_score(candidate), execution_score),
        data_confidence=_safe_float(candidate.get("data_confidence")),
        setup_score=setup_score,
        trigger_score=trigger_score,
        entry_quality_score=entry_quality_score,
        family_survival_score=family_survival_score,
        risk_learning_adjustment=_safe_float(candidate.get("risk_learning_adjustment")),
        risk_learning_confidence=_safe_float(candidate.get("risk_learning_confidence")),
        is_fallback=_safe_bool(candidate.get("synthetic_candidate"), default=False),
        stale_quote=not _safe_bool(candidate.get("fresh_quote_ok"), default=True),
        missing_liquidity=not _safe_bool(candidate.get("liquidity_ok"), default=True),
        spread_uncertain=_safe_float(candidate.get("spread_pct")) is None,
    )
    final_score = _safe_float(result.get("final_score")) or 0.0
    soft_penalties = list(candidate.get("phase2_soft_penalties") or [])
    if "liquidity_penalty" in soft_penalties:
        liquidity_penalty = float(getattr(cfg, "PHASE2_LIQUIDITY_SOFT_PENALTY", 0.08) or 0.08)
        final_score = max(0.0, float(final_score) - float(liquidity_penalty))
        result["phase2_liquidity_soft_penalty"] = float(liquidity_penalty)
        result["phase2_soft_penalties"] = soft_penalties
    return float(final_score), dict(result or {})


def _apply_data_fallbacks(candidate: dict[str, Any]) -> None:
    if _safe_float(candidate.get("quote_age_sec")) is None:
        candidate["quote_age_sec"] = 1.0
    depth_score = _safe_float(candidate.get("depth_score"))
    if depth_score is not None and float(depth_score) == 0.0:
        candidate["depth_score"] = 0.5
    if _safe_float(candidate.get("tick_volume")) is None:
        candidate["tick_volume"] = 1.0


def build_candidates_phase2(raw_candidates: list[Any] | None = None) -> list[dict[str, Any]]:
    raw_list = list(raw_candidates or [])
    if not raw_list:
        logger.warning("PHASE2: No input candidates for phase2 raw_count=0")
        return []
    ranked_candidates: list[dict[str, Any]] = []
    drop_reason_counts: dict[str, int] = {}
    drop_debug_budget = int(getattr(cfg, "PHASE2_FILTER_DROP_DEBUG_LIMIT", 25) or 25)
    for raw in raw_list:
        candidate = _candidate_to_dict(raw)
        if not validate_candidate(candidate):
            logger.warning(
                "PHASE2: invalid candidate skipped trade_id=%s symbol=%s",
                candidate.get("trade_id"),
                candidate.get("symbol"),
            )
            continue
        _apply_data_fallbacks(candidate)
        hard_reasons = _hard_filter_reasons(candidate)
        if hard_reasons:
            for reason in hard_reasons:
                drop_reason_counts[reason] = int(drop_reason_counts.get(reason, 0)) + 1
            if drop_debug_budget > 0:
                print(
                    "DEBUG_FILTER_DROP",
                    {
                        "trade_id": candidate.get("trade_id"),
                        "symbol": candidate.get("symbol"),
                        "reasons": hard_reasons,
                        "execution_allowed": candidate.get("execution_allowed"),
                        "execution_ok": candidate.get("execution_ok"),
                        "liquidity_score": candidate.get("liquidity_score"),
                        "candidate_status": candidate.get("candidate_status"),
                        "execution_status": candidate.get("execution_status"),
                        "candidate_origin": candidate.get("candidate_origin"),
                    },
                )
                drop_debug_budget -= 1
            continue
        final_score, score_detail = _compute_phase2_final_score(candidate)
        candidate["final_score"] = float(final_score)
        candidate["score"] = float(final_score)
        candidate["phase2_score_detail"] = score_detail
        candidate["phase2_hard_filters"] = {
            "spread_ok": "hard_spread" not in hard_reasons,
            "execution_ok": "hard_execution" not in hard_reasons,
            "liquidity_ok": "hard_liquidity" not in hard_reasons,
        }
        ranked_candidates.append(candidate)

    if not ranked_candidates:
        logger.warning(
            "PHASE2: No valid candidates after filtering raw_count=%s drop_counts=%s",
            len(raw_list),
            drop_reason_counts,
        )
        return []

    ranked_candidates.sort(
        key=lambda row: (
            float(_safe_float(row.get("final_score")) or 0.0),
            float(_safe_float(row.get("execution_score")) or 0.0),
            float(_safe_float(row.get("confidence_final")) or _safe_float(row.get("confidence")) or 0.0),
        ),
        reverse=True,
    )
    return ranked_candidates


def _active_trade_score(active_trade: dict[str, Any] | None) -> float | None:
    if not isinstance(active_trade, dict):
        return None
    for key in ("final_score", "rank_score", "opportunity_score"):
        value = _safe_float(active_trade.get(key))
        if value is not None:
            return float(value)
    return None


def _should_replace(current_score: float | None, new_score: float, *, min_abs_delta: float, min_rel_delta: float) -> bool:
    if current_score is None:
        return True
    if (new_score - current_score) < float(min_abs_delta):
        return False
    baseline = max(abs(current_score), 1e-9)
    if ((new_score - current_score) / baseline) < float(min_rel_delta):
        return False
    return True


def _should_clear_trade(active_trade: dict[str, Any] | None) -> bool:
    if not isinstance(active_trade, dict) or not active_trade:
        return False
    max_age = float(getattr(cfg, "PHASE2_ACTIVE_TRADE_MAX_AGE_SEC", 30.0) or 30.0)
    if max_age <= 0.0:
        return False
    anchor_epoch = (
        _safe_float(active_trade.get("decision_ts_epoch"))
        or _safe_float(active_trade.get("timestamp_epoch"))
        or _safe_float(active_trade.get("ts_epoch"))
    )
    if anchor_epoch is None or anchor_epoch <= 0:
        return False
    return (time.time() - float(anchor_epoch)) > float(max_age)


def run_engine_phase2(
    raw_candidates: list[Any] | None,
    *,
    active_trade: Any = None,
    min_enter_score: float | None = None,
    top_n: int | None = None,
) -> dict[str, Any]:
    def _normalize_selected(selected: Any) -> dict[str, Any] | None:
        if selected is None:
            return None
        selected_dict = _candidate_to_dict(selected)
        selected_dict.setdefault("score", _safe_float(selected_dict.get("final_score")) or 0.0)
        selected_dict.setdefault("symbol", str(selected_dict.get("symbol") or ""))
        selected_dict.setdefault("decision_ts_epoch", float(time.time()))
        if not str(selected_dict.get("symbol") or "").strip():
            return None
        if _safe_float(selected_dict.get("score")) is None:
            return None
        return selected_dict

    def _log_state(state: str, selected: dict[str, Any] | None, ranked_count: int) -> None:
        symbol = selected.get("symbol") if isinstance(selected, dict) else None
        score = (
            _safe_float(selected.get("score"))
            if isinstance(selected, dict)
            else None
        )
        logger.info(
            "PHASE2_DECISION | state=%s | ranked_count=%s | top_score=%s | symbol=%s",
            state,
            int(ranked_count),
            score,
            symbol,
        )

    ranked = build_candidates_phase2(raw_candidates)
    top_limit = max(1, int(top_n if top_n is not None else getattr(cfg, "PHASE2_TOP_N", 3) or 3))
    min_enter = float(
        min_enter_score
        if min_enter_score is not None
        else getattr(cfg, "PHASE2_MIN_ENTER_SCORE", 0.70)
    )
    force_fallback = bool(getattr(cfg, "PHASE2_FORCE_FALLBACK_EXECUTION_ENABLE", True))
    force_fallback_min_score = float(getattr(cfg, "PHASE2_FORCE_FALLBACK_MIN_SCORE", 0.05) or 0.05)
    allow_fallback_live = bool(getattr(cfg, "PHASE2_FORCE_FALLBACK_ALLOW_LIVE", False))
    ranked_top = list(ranked[:top_limit])
    active_trade_dict = _candidate_to_dict(active_trade) if active_trade is not None else None
    if _should_clear_trade(active_trade_dict):
        logger.info(
            "PHASE2: clearing stale active_trade trade_id=%s",
            (active_trade_dict or {}).get("trade_id"),
        )
        active_trade_dict = None

    if not ranked_top:
        _log_state("NO_TRADE", None, ranked_count=0)
        return {
            "state": "NO_TRADE",
            "reason": "no_rankable_candidates",
            "selected": None,
            "ranked": [],
            "next_active_trade": None,
        }

    top = ranked_top[0]
    top_score = float(_safe_float(top.get("final_score")) or 0.0)
    active_score = _active_trade_score(active_trade_dict)
    min_abs_delta = float(getattr(cfg, "PHASE2_REPLACE_MIN_ABS_DELTA", 0.12) or 0.12)
    min_rel_delta = float(getattr(cfg, "PHASE2_REPLACE_MIN_REL_DELTA", 0.20) or 0.20)

    if active_trade_dict is not None:
        if top_score >= min_enter and _should_replace(
            active_score,
            top_score,
            min_abs_delta=min_abs_delta,
            min_rel_delta=min_rel_delta,
        ):
            selected = _normalize_selected(top)
            if selected is None:
                _log_state("NO_TRADE", None, ranked_count=len(ranked_top))
                return {
                    "state": "NO_TRADE",
                    "reason": "invalid_selected_payload",
                    "selected": None,
                    "ranked": ranked_top,
                    "next_active_trade": active_trade_dict,
                }
            _log_state("REPLACE", selected, ranked_count=len(ranked_top))
            return {
                "state": "REPLACE",
                "reason": "top_ranked_upgrade",
                "selected": selected,
                "ranked": ranked_top,
                "next_active_trade": selected,
            }
        active_selected = _normalize_selected(active_trade_dict) or active_trade_dict
        _log_state("HOLD", active_selected if isinstance(active_selected, dict) else None, ranked_count=len(ranked_top))
        return {
            "state": "HOLD",
            "reason": "no_significant_upgrade",
            "selected": active_selected,
            "ranked": ranked_top,
            "next_active_trade": active_selected,
        }

    if top_score >= min_enter:
        selected = _normalize_selected(top)
        if selected is None:
            _log_state("NO_TRADE", None, ranked_count=len(ranked_top))
            return {
                "state": "NO_TRADE",
                "reason": "invalid_selected_payload",
                "selected": None,
                "ranked": ranked_top,
                "next_active_trade": None,
            }
        _log_state("ENTER", selected, ranked_count=len(ranked_top))
        return {
            "state": "ENTER",
            "reason": "top_ranked",
            "selected": selected,
            "ranked": ranked_top,
            "next_active_trade": selected,
        }

    selected = _normalize_selected(top)

    if force_fallback and selected is not None:
        mode = _mode_for_candidate(selected)
        allow_mode = (not _live_mode(mode)) or allow_fallback_live
        if allow_mode and top_score >= force_fallback_min_score:
            logger.warning(
                "FORCED_EXECUTION_FALLBACK trade_id=%s symbol=%s score=%.4f mode=%s",
                selected.get("trade_id"),
                selected.get("symbol"),
                top_score,
                mode,
            )
            selected["execution_status"] = "executable"
            selected["candidate_status"] = "executable"
            selected["forced_fallback_execution"] = True
            _log_state("ENTER", selected, ranked_count=len(ranked_top))
            return {
                "state": "ENTER",
                "reason": "forced_fallback_execution",
                "selected": selected,
                "ranked": ranked_top,
                "next_active_trade": selected,
            }

    _log_state("WATCHLIST", selected, ranked_count=len(ranked_top))
    return {
        "state": "WATCHLIST",
        "reason": "top_score_below_enter_threshold",
        "selected": selected,
        "ranked": ranked_top,
        "next_active_trade": None,
    }
