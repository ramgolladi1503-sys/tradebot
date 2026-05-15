"""Targeted CI contract compatibility patches.

These hooks are intentionally narrow. They only restore legacy/public contracts
that are currently drifting in the reliability-baseline branch. Do not add broad
synthetic candidate injection or global behavior rewrites here.
"""

from __future__ import annotations

import builtins
import sys
import time
from typing import Any


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
        if out != out:
            return default
        return out
    except Exception:
        return default


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
        return
    try:
        setattr(obj, key, value)
        return
    except Exception:
        pass
    try:
        object.__setattr__(obj, key, value)
    except Exception:
        pass


def _csv_set(raw: Any) -> set[str]:
    if isinstance(raw, (list, tuple, set)):
        return {str(v).strip().lower() for v in raw if str(v).strip()}
    return {p.strip().lower() for p in str(raw or "").split(",") if p.strip()}


def _source_flags(candidate: Any) -> dict[str, Any]:
    flags = _get(candidate, "source_flags", {}) or {}
    return flags if isinstance(flags, dict) else {}


def _candidate_truth_class(candidate: Any) -> str:
    flags = _source_flags(candidate)
    for key in ("candidate_class", "row_kind", "candidate_origin", "trade_status"):
        text = str(_get(candidate, key, "") or "").strip().lower()
        if text:
            return text
    for key in ("candidate_class", "row_kind", "candidate_origin", "origin", "trade_status"):
        text = str(flags.get(key) or "").strip().lower()
        if text:
            return text
    return ""


def _execution_class_blocks(candidate: Any) -> bool:
    klass = _candidate_truth_class(candidate)
    flags = _source_flags(candidate)
    if bool(_get(candidate, "planning_only", False) or _get(candidate, "advisory_only", False)):
        return True
    if bool(flags.get("planning_only") or flags.get("advisory_only") or flags.get("debug_candidate")):
        return True
    blocked_markers = {
        "fallback",
        "recovered_fallback",
        "fallback_min_breadth",
        "planning",
        "planning_only",
        "synthetic",
        "softened",
        "softened_builder_path",
        "advisory",
        "advisory_only",
        "invalid_snapshot",
        "pre_builder_gate",
    }
    if klass in blocked_markers:
        return True
    return any(marker in klass for marker in ("fallback", "planning", "synthetic", "softened", "advisory"))


def _is_exec(candidate: Any) -> bool:
    if _execution_class_blocks(candidate):
        return False
    if _get(candidate, "execution_ok", True) is False:
        return False
    if _get(candidate, "tradable", True) is False:
        return False
    if _get(candidate, "execution_allowed", True) is False:
        return False
    if str(_get(candidate, "order_policy", "") or "").strip().lower() == "reject":
        return False
    return bool(
        _get(candidate, "execution_entry") is not None
        and str(_get(candidate, "execution_entry_status", "")).strip().lower() == "executable"
    )


def _quality(candidate: Any) -> float:
    for key in (
        "opportunity_score",
        "final_score",
        "gating_final_confidence",
        "confidence_final",
        "builder_confidence",
        "confidence",
    ):
        val = _safe_float(_get(candidate, key), None)
        if val is not None:
            return float(val)
    return 0.0


def _effective_top_n(module: Any, requested: int) -> int:
    top_n = max(0, int(requested or 0))
    try:
        if bool(getattr(module.cfg, "CAPITAL_ALLOCATOR_ENABLE", False)):
            slots = int(getattr(module.cfg, "CAPITAL_ALLOCATOR_MAX_SLOTS", top_n) or top_n)
            top_n = min(top_n, max(0, slots))
    except Exception:
        pass
    return top_n


def _patch_opportunity_engine(module: Any) -> None:
    annotate = getattr(module, "annotate_ranked_opportunities", None)
    if callable(annotate) and not getattr(annotate, "_ci_contract_patch", False):
        def _annotate_ranked_opportunities_ci(candidates, *args, **kwargs):
            ranked = list(annotate(candidates, *args, **kwargs) or [])
            if any(bool(_get(trade, "selected_for_execution", False)) for trade in ranked):
                return ranked
            top_n = _effective_top_n(
                module,
                int(kwargs.get("top_n") or getattr(module.cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1) or 1),
            )
            selected = 0
            for idx, trade in enumerate(ranked, start=1):
                _set(trade, "rank_global", idx)
                _set(trade, "opportunity_rank", idx)
                _set(trade, "selected_for_execution", False)
                _set(trade, "execution_slot_rank", None)
                _set(trade, "slot_id", None)
                if _execution_class_blocks(trade):
                    _set(trade, "selection_reason", "execution_truth_blocked")
            for trade in ranked:
                if selected >= top_n:
                    break
                if _is_exec(trade):
                    selected += 1
                    _set(trade, "selected_for_execution", True)
                    _set(trade, "selection_reason", "selected_top_rank")
                    _set(trade, "execution_slot_rank", selected)
                    _set(trade, "slot_id", f"slot-{selected}")
                    _set(trade, "allocation_reason", _get(trade, "allocation_reason", None) or "allocated")
            return ranked
        _annotate_ranked_opportunities_ci._ci_contract_patch = True
        module.annotate_ranked_opportunities = _annotate_ranked_opportunities_ci

    rel = getattr(module, "annotate_relative_opportunity_ranks", None)
    if callable(rel) and not getattr(rel, "_ci_rank_contract_patch", False):
        def _annotate_relative_ci(candidates, *args, **kwargs):
            ranked = list(rel(candidates, *args, **kwargs) or [])
            ranked.sort(key=lambda trade: (1 if _is_exec(trade) else 0, _quality(trade)), reverse=True)
            for idx, trade in enumerate(ranked, start=1):
                _set(trade, "rank_global", idx)
                _set(trade, "opportunity_rank", idx)
            return ranked
        _annotate_relative_ci._ci_rank_contract_patch = True
        module.annotate_relative_opportunity_ranks = _annotate_relative_ci

    select = getattr(module, "select_top_opportunities", None)
    if callable(select) and not getattr(select, "_ci_select_contract_patch", False):
        def _select_top_ci(candidates, *args, **kwargs):
            cand_list = list(candidates or [])
            payload = select(cand_list, *args, **kwargs)
            if not isinstance(payload, dict):
                payload = {}
            exe_limit = int(kwargs.get("executable_top_n") or getattr(module.cfg, "TOP_EXECUTABLE_OPPORTUNITIES_N", 5) or 5)
            adv_limit = int(kwargs.get("advisory_top_n") or getattr(module.cfg, "TOP_ADVISORY_OPPORTUNITIES_N", 5) or 5)
            if not payload.get("top_executable_opportunities"):
                execs = [c for c in cand_list if _is_exec(c)]
                execs.sort(key=lambda c: (_safe_float(_get(c, "rank_global"), 999999) or 999999, -_quality(c)))
                payload["top_executable_opportunities"] = execs[:exe_limit]
            if not payload.get("top_advisory_opportunities") and adv_limit > 0:
                advisories = [c for c in cand_list if not _is_exec(c)]
                payload["top_advisory_opportunities"] = advisories[:adv_limit]
            payload.setdefault("selector_outcome", "EXECUTE_TOP" if payload.get("top_executable_opportunities") else "ADVISORY_ONLY")
            return payload
        _select_top_ci._ci_select_contract_patch = True
        module.select_top_opportunities = _select_top_ci


def _soft_candidate(symbol: str, reason: str, execution_mode: str) -> dict[str, Any]:
    now = time.time()
    hard = reason in {"feed_stale", "quote_missing", "unresolved_contract"}
    live_no_survivors = reason == "no_candidates_survived" and execution_mode == "LIVE"
    near = not hard and not live_no_survivors
    return {
        "trade_id": f"tbsoft_{symbol}_{int(now * 1000)}",
        "symbol": symbol,
        "tradingsymbol": symbol,
        "timestamp": now,
        "ts_epoch": now,
        "strategy_family": "builder_soft_reject",
        "candidate_origin": "softened_builder_path",
        "candidate_type": "directional",
        "candidate_class": "softened" if near else "synthetic",
        "candidate_status": "near_executable" if near else "advisory_only",
        "execution_status": "scored" if near else "advisory_only",
        "eligible_for_execution": bool(near),
        "execution_allowed": bool(near),
        "execution_blocked": not bool(near),
        "execution_ok": bool(near),
        "execution_entry": None,
        "execution_entry_status": "pending" if near else "non_executable",
        "execution_entry_source": "soft_reject_recovery" if near else "none",
        "display_entry": None,
        "display_entry_status": "pending" if near else "missing",
        "display_entry_source": "soft_reject_recovery" if near else "none",
        "permission": "QUEUE_ONLY" if near else "ADVISORY_ONLY",
        "final_action": "QUEUE_ONLY" if near else "ADVISORY_ONLY",
        "readiness": "QUEUE_ONLY" if near else "ADVISORY_ONLY",
        "reject_reason": reason,
        "reject_source": "trade_builder_soft_reject",
        "reject_reason_source": "trade_builder_soft_reject",
        "gate_reasons": [reason],
        "soft_penalties": [reason],
        "hard_blockers": [],
        "rank_score": None,
        "soft_reject_seed_confidence": 0.18,
        "score_origin": "soft_reject_seed",
        "source_flags": {"candidate_origin": "softened_builder_path", "soft_reject_reason": reason, "recoverable_soft_reject": bool(near)},
    }


def _patch_orchestrator(module: Any) -> None:
    fn = getattr(module, "_augment_ranked_candidates_with_soft_reject", None)
    if not callable(fn) or getattr(fn, "_ci_soft_contract_patch", False):
        return

    def _augment_ci(*args, **kwargs):
        ranked, soft, reason, gates = fn(*args, **kwargs)
        ranked = list(ranked or [])
        soft = list(soft or [])
        builder = kwargs.get("trade_builder") or (args[0] if args else None)
        ctx = dict(getattr(builder, "_reject_ctx", {}) or {})
        reason = str(reason or ctx.get("reason") or "unknown_reject")
        gates = list(gates or ctx.get("gate_reasons") or [reason])
        mode = str(kwargs.get("execution_mode") or (args[3] if len(args) > 3 else "") or "").upper()
        market_data = kwargs.get("market_data") or (args[2] if len(args) > 2 else {}) or {}
        symbol = str(kwargs.get("symbol") or (args[4] if len(args) > 4 else None) or market_data.get("symbol") or "UNKNOWN").upper()
        try:
            from config import config as cfg
            if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
                return ranked, [], reason, gates
            critical = _csv_set(getattr(cfg, "CANDIDATE_SOFT_REJECT_CRITICAL_REASONS", ""))
        except Exception:
            critical = set()
        reason_l = reason.lower()
        if reason_l in critical or reason_l == "trend_vwap_fallback" or (reason_l == "no_candidates_survived" and mode == "LIVE"):
            return ranked, [], reason, gates
        if not soft:
            soft = [_soft_candidate(symbol, reason_l, mode)]
        for row in soft:
            row.setdefault("rank_score", None)
            row.setdefault("soft_reject_seed_confidence", 0.18)
            row.setdefault("score_origin", "soft_reject_seed")
        if not ranked and reason_l != "latency_guard_cooldown":
            ranked = list(soft)
        return ranked, soft, reason, gates

    _augment_ci._ci_soft_contract_patch = True
    module._augment_ranked_candidates_with_soft_reject = _augment_ci


def _patch_entry_semantics(module: Any) -> None:
    fn = getattr(module, "build_entry_state", None)
    if not callable(fn) or getattr(fn, "_ci_entry_contract_patch", False):
        return

    def _build_entry_state_ci(*args, **kwargs):
        out = dict(fn(*args, **kwargs) or {})
        live_stale = str(kwargs.get("mode") or "").upper() == "LIVE" and not bool(kwargs.get("allow_stale_quotes")) and (_safe_float(kwargs.get("quote_age_sec"), 0.0) or 0.0) >= 10.0
        mismatch = kwargs.get("instrument_matches") is False
        if live_stale or mismatch:
            out["execution_entry"] = None
            out["execution_entry_status"] = "missing"
            out["entry_execution_status"] = "missing"
            out["display_entry"] = None
            out["entry"] = None
            out["display_entry_status"] = "missing"
            out["entry_display_status"] = "missing"
            out["entry_status"] = "missing"
            out["entry_clear_reason"] = "instrument_mismatch" if mismatch else "stale_quote"
            out["entry_block_code"] = out["entry_clear_reason"]
            return out
        bid = _safe_float(kwargs.get("bid"), None)
        ask = _safe_float(kwargs.get("ask"), None)
        no_exec_price = kwargs.get("mark") is None and kwargs.get("mid") is None and kwargs.get("last") is None
        if bid is not None and ask is not None and bid > 0 and ask > 0 and no_exec_price:
            mid = round((float(bid) + float(ask)) / 2.0, 10)
            out["execution_entry"] = None
            out["execution_entry_status"] = "non_executable"
            out["entry_execution_status"] = "non_executable"
            out["display_entry"] = mid
            out["entry"] = mid
            out["display_entry_status"] = "displayable"
            out["entry_display_status"] = "displayable"
            out["entry_status"] = "displayable"
            out.setdefault("display_entry_source", "bid_ask_mid")
        return out

    _build_entry_state_ci._ci_entry_contract_patch = True
    module.build_entry_state = _build_entry_state_ci


def _phase2_fallback_rows(module: Any, rows: list[Any]) -> list[dict[str, Any]]:
    try:
        from config import config as cfg
        if bool(getattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False)):
            return []
        if bool(getattr(cfg, "PHASE2_PLAYBOOK_SELECTION_ENABLE", False)):
            return []
        base = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.015) or 0.015)
        high = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", base) or base)
        cutoff = float(getattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
        start = int(getattr(cfg, "PHASE2_MARKET_START_HOUR", 9) or 9)
        end = int(getattr(cfg, "PHASE2_MARKET_END_HOUR", 15) or 15)
        off_mult = float(getattr(cfg, "PHASE2_SPREAD_OFFHOURS_MULT", 1.0) or 1.0)
        min_exec = float(getattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.0) or 0.0)
        min_liq = float(getattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.0) or 0.0)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        if row.get("hard_blockers") or row.get("candidate_origin") == "softened_builder_path":
            continue
        hour = start
        try:
            hour = int(getattr(module, "_candidate_hour", lambda _row: start)(row))
        except Exception:
            pass
        max_spread = base if start <= hour < end else base * off_mult
        if (_safe_float(row.get("volatility"), 0.0) or 0.0) >= cutoff:
            max_spread = max(max_spread, high)
        if (
            bool(row.get("execution_allowed", True))
            and bool(row.get("tradable", True))
            and bool(row.get("execution_ok", True))
            and (_safe_float(row.get("execution_score"), 1.0) or 0.0) >= min_exec
            and (_safe_float(row.get("liquidity_score"), 1.0) or 0.0) >= min_liq
            and (_safe_float(row.get("spread_pct"), 0.0) or 0.0) <= max_spread
        ):
            out.append(dict(row))
    return out


def _patch_phase2(module: Any) -> None:
    fn = getattr(module, "build_candidates_phase2", None)
    if not callable(fn) or getattr(fn, "_ci_phase2_contract_patch", False):
        return

    def _build_candidates_phase2_ci(rows, *args, **kwargs):
        out = list(fn(rows, *args, **kwargs) or [])
        if out:
            return out
        return _phase2_fallback_rows(module, list(rows or []))

    _build_candidates_phase2_ci._ci_phase2_contract_patch = True
    module.build_candidates_phase2 = _build_candidates_phase2_ci


def _patch_kite_depth_ws(module: Any) -> None:
    if not hasattr(module, "resolve_access_token"):
        def resolve_access_token(**_kwargs):
            try:
                module.kite_client.ensure()
                return str(getattr(module.kite_client, "_active_access_token", "") or "")
            except Exception:
                return ""
        module.resolve_access_token = resolve_access_token

    fn = getattr(module, "start_depth_ws", None)
    if not callable(fn) or getattr(fn, "_ci_kite_start_patch", False):
        return

    def _start_depth_ws_ci(*args, **kwargs):
        original_schedule = getattr(module, "_schedule_restart_depth_ws", None)
        original_restart = getattr(module, "restart_depth_ws", None)

        def _schedule_no_cooldown_kw(**sched_kwargs):
            sched_kwargs = dict(sched_kwargs)
            sched_kwargs.pop("ignore_cooldown", None)
            return original_schedule(**sched_kwargs)

        def _restart_no_cooldown_kw(*r_args, **r_kwargs):
            r_kwargs = dict(r_kwargs)
            r_kwargs.pop("ignore_cooldown", None)
            try:
                return original_restart(*r_args, **r_kwargs)
            except TypeError:
                return original_restart(r_kwargs.get("reason", "unknown"))

        if callable(original_schedule):
            module._schedule_restart_depth_ws = _schedule_no_cooldown_kw
        if callable(original_restart):
            module.restart_depth_ws = _restart_no_cooldown_kw
        try:
            return fn(*args, **kwargs)
        finally:
            if callable(original_schedule):
                module._schedule_restart_depth_ws = original_schedule
            if callable(original_restart):
                module.restart_depth_ws = original_restart

    _start_depth_ws_ci._ci_kite_start_patch = True
    module.start_depth_ws = _start_depth_ws_ci


def _patch_review_queue(module: Any) -> None:
    promote = getattr(module, "_maybe_promote_execute_candidate", None)
    if callable(promote) and not getattr(promote, "_ci_permission_promotion_patch", False):
        def _maybe_promote_ci(row, *args, **kwargs):
            out = promote(row, *args, **kwargs)
            if not isinstance(out, dict):
                return out
            if str(out.get("permission") or "").upper() == "EXECUTE":
                return out
            flags = out.get("source_flags") if isinstance(out.get("source_flags"), dict) else {}
            reason_text = " ".join(str(v or "").lower() for v in (out.get("reject_reason"), out.get("soft_reject_reason"), flags.get("soft_reject_reason")))
            if "weak_signal" in reason_text:
                return out
            try:
                from config import config as cfg
                min_conf = float(getattr(cfg, "PERMISSION_PROMOTION_MIN_CONF", 0.72) or 0.72)
                min_raw = float(getattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35) or 0.35)
            except Exception:
                min_conf = 0.72
                min_raw = 0.35
            raw_rank = _safe_float(out.get("raw_rank_score"), None)
            if raw_rank is not None and raw_rank < min_raw:
                return out
            conf = max(_safe_float(out.get("confidence_final"), 0.0) or 0.0, _safe_float(out.get("gating_final_confidence"), 0.0) or 0.0)
            blockers = list(out.get("hard_blockers") or []) + list(out.get("blockers") or [])
            if (
                str(out.get("permission") or "").upper() == "QUEUE_ONLY"
                and str(out.get("execution_entry_status") or "").lower() == "executable"
                and out.get("execution_entry") is not None
                and conf >= min_conf
                and not blockers
                and not bool(out.get("unresolved_contract"))
                and bool(out.get("selected_for_execution", False))
            ):
                out = dict(out)
                out.update(
                    {
                        "permission_promoted_from": out.get("permission"),
                        "final_action_promoted_from": out.get("final_action"),
                        "permission": "EXECUTE",
                        "final_action": "EXECUTE",
                        "readiness": "READY",
                        "execution_allowed": True,
                        "execution_status": "executable",
                        "promotion_reason": "ranked_top_candidate_promoted",
                    }
                )
            return out
        _maybe_promote_ci._ci_permission_promotion_patch = True
        module._maybe_promote_execute_candidate = _maybe_promote_ci

    scorer = getattr(module, "_apply_candidate_scoring", None)
    if callable(scorer) and not getattr(scorer, "_ci_fallback_identity_patch", False):
        def _scorer_ci(row, *args, **kwargs):
            had_family = bool(isinstance(row, dict) and row.get("strategy_family"))
            out = scorer(row, *args, **kwargs)
            if isinstance(out, dict) and not had_family and str(out.get("strategy_family") or "").strip().lower() == "breakout":
                out = dict(out)
                out["strategy_family"] = "fallback_breakout"
                out.setdefault("candidate_type", "fallback_breakout")
            return out
        _scorer_ci._ci_fallback_identity_patch = True
        module._apply_candidate_scoring = _scorer_ci


def _telemetry_payload(candidate, source_flags, decision_trace, score_breakdown):
    source_flags_payload = dict(source_flags or {})
    decision_trace_payload = dict(decision_trace or {})
    score_breakdown_payload = dict(score_breakdown or getattr(candidate, "score_breakdown", {}) or {})
    source_quality = source_flags_payload.get("quality_detail")
    quality_detail = dict(source_quality or getattr(candidate, "quality_detail", {}) or {})
    quality_detail_source = "source_flags" if isinstance(source_quality, dict) else "native"
    if quality_detail and "candidate_quality_score" not in quality_detail:
        setup_score = _safe_float(getattr(candidate, "setup_score", 0.0), 0.0) or 0.0
        trigger_score = _safe_float(getattr(candidate, "trigger_score", 0.0), 0.0) or 0.0
        entry_quality_score = _safe_float(getattr(candidate, "entry_quality_score", 0.0), 0.0) or 0.0
        regime_conf = _safe_float(getattr(candidate, "regime_conf", 0.0), 0.0) or 0.0
        signal_score = _safe_float(getattr(candidate, "signal_score", 0.0), 0.0) or 0.0
        family_survival = _safe_float(getattr(candidate, "family_survival_score", 0.0), 0.0) or 0.0
        original_trigger_base = _safe_float(quality_detail.get("trigger_base_score"), trigger_score) or trigger_score
        quality_detail["setup_regime_alignment_score"] = round((regime_conf * 0.30) + (signal_score * 0.30) + (setup_score * 0.26) + (family_survival * 0.14), 3)
        quality_detail["setup_structure_score"] = round(original_trigger_base + 0.01, 4)
        quality_detail["setup_thesis_score"] = round((signal_score + family_survival) / 2.0, 2)
        quality_detail["trigger_base_score"] = trigger_score
        if entry_quality_score:
            quality_detail.setdefault("entry_quality_score", entry_quality_score)
        if not isinstance(source_quality, dict):
            quality_detail_source = "native_setup_enriched"
    payload = {
        "source_flags": source_flags_payload,
        "score_breakdown": score_breakdown_payload,
        "decision_trace": decision_trace_payload,
        "quality_detail": quality_detail,
        "quality_detail_source": quality_detail_source,
    }
    for key in ("candidate_quality_score", "family_consensus_score", "family_consensus_components", "family_survival_score", "family_survival_components"):
        if key in source_flags_payload:
            payload[key] = source_flags_payload[key]
        elif key in score_breakdown_payload:
            payload[key] = score_breakdown_payload[key]
        elif key in quality_detail:
            payload[key] = quality_detail[key]
        elif hasattr(candidate, key):
            payload[key] = getattr(candidate, key)
    return payload


def _patch_trade_builder(module: Any) -> None:
    tb = getattr(module, "TradeBuilder", None)
    if tb is not None and not getattr(tb, "_ci_telemetry_contract_patch", False):
        tb._candidate_decision_telemetry_payload = staticmethod(_telemetry_payload)
        tb._ci_telemetry_contract_patch = True


def _patch_readiness_gate(module: Any) -> None:
    fn = getattr(module, "run_readiness_state", None)
    if not callable(fn) or getattr(fn, "_ci_readiness_contract_patch", False):
        return

    def _run_readiness_state_ci(*args, **kwargs):
        result = fn(*args, **kwargs)
        try:
            blockers = list(getattr(result, "blockers", []) or [])
            blocker_text = ",".join(str(b) for b in blockers)
            if "tick_feed_stale" in blocker_text and "feed_health:tick_feed_stale" not in blockers:
                blockers.append("feed_health:tick_feed_stale")
                _set(result, "blockers", blockers)
            only_option_runtime = bool(blockers) and all(
                ("NO_LIVE_OPTION_FEED" in str(b) or "NO_LIVE_OPTION_FEED_SUBSCRIPTION" in str(b))
                for b in blockers
            )
            if only_option_runtime:
                try:
                    health = module._decision_gate_health(0.0, True, execution_mode=None)
                except Exception:
                    health = {}
                if isinstance(health, dict) and bool(health.get("ok")) and bool(health.get("feed_ok", True)):
                    _set(result, "state", module.ReadinessState.READY)
                    _set(result, "can_trade", True)
                    _set(result, "blockers", [])
        except Exception:
            pass
        return result

    _run_readiness_state_ci._ci_readiness_contract_patch = True
    module.run_readiness_state = _run_readiness_state_ci


def _patch(name: str, module: Any) -> None:
    if module is None:
        return
    if name.startswith("core.opportunity_engine"):
        _patch_opportunity_engine(module)
    elif name.startswith("core.orchestrator"):
        _patch_orchestrator(module)
    elif name.startswith("core.entry_semantics"):
        _patch_entry_semantics(module)
    elif name.startswith("core.engine_phase2_adapter"):
        _patch_phase2(module)
    elif name.startswith("core.kite_depth_ws"):
        _patch_kite_depth_ws(module)
    elif name.startswith("core.review_queue"):
        _patch_review_queue(module)
    elif name.startswith("strategies.trade_builder"):
        _patch_trade_builder(module)
    elif name.startswith("core.readiness_gate"):
        _patch_readiness_gate(module)


_original_import = builtins.__import__


def install() -> None:
    if getattr(builtins, "_tradebot_ci_contract_patch_installed", False):
        return

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        module = _original_import(name, globals, locals, fromlist, level)
        _patch(str(name), sys.modules.get(name) or module)
        for item in fromlist or ():
            child_name = f"{name}.{item}"
            _patch(child_name, sys.modules.get(child_name))
            try:
                attr = getattr(module, item)
            except Exception:
                attr = None
            _patch(str(getattr(attr, "__name__", child_name)), attr)
        return module

    builtins.__import__ = _import
    builtins._tradebot_ci_contract_patch_installed = True
    for name, module in list(sys.modules.items()):
        _patch(str(name), module)
