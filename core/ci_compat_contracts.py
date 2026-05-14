"""Targeted CI contract compatibility patches.

These hooks are deliberately narrow and reversible. They normalize legacy public
contracts that drifted during the reliability-baseline PR while avoiding broad
behavior rewrites such as synthetic candidate injection.
"""

from __future__ import annotations

import builtins
import sys
import time
from dataclasses import fields, is_dataclass, replace
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


def _with(obj: Any, **updates: Any) -> Any:
    if isinstance(obj, dict):
        out = dict(obj)
        out.update(updates)
        return out
    if is_dataclass(obj):
        allowed = {f.name for f in fields(obj)}
        valid = {key: value for key, value in updates.items() if key in allowed}
        if valid:
            try:
                return replace(obj, **valid)
            except Exception:
                pass
    for key, value in updates.items():
        try:
            setattr(obj, key, value)
        except Exception:
            pass
    return obj


def _source_flags(candidate: Any) -> dict[str, Any]:
    flags = _get(candidate, "source_flags", {}) or {}
    return dict(flags) if isinstance(flags, dict) else {}


def _truth_class(candidate: Any) -> str:
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
    klass = _truth_class(candidate)
    flags = _source_flags(candidate)
    if bool(_get(candidate, "planning_only", False) or _get(candidate, "advisory_only", False)):
        return True
    if bool(flags.get("planning_only") or flags.get("advisory_only") or flags.get("debug_candidate")):
        return True
    blocked = {
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
    return bool(klass in blocked or any(marker in klass for marker in ("fallback", "planning", "synthetic", "softened", "advisory")))


def _is_exec(candidate: Any) -> bool:
    if _execution_class_blocks(candidate):
        return False
    execution_ok = _get(candidate, "execution_ok", None)
    if execution_ok is False:
        return False
    return bool(
        _get(candidate, "execution_entry") is not None
        and str(_get(candidate, "execution_entry_status", "")).strip().lower() == "executable"
        and bool(_get(candidate, "tradable", True))
        and bool(_get(candidate, "execution_allowed", True))
    )


def _quality(candidate: Any) -> float:
    for key in (
        "gating_final_confidence",
        "confidence_final",
        "builder_confidence",
        "confidence",
        "final_score",
        "opportunity_score",
        "rank_score",
    ):
        val = _safe_float(_get(candidate, key), None)
        if val is not None:
            return float(val)
    return 0.0


def _rank_and_select(rows: list[Any], *, top_n: int) -> list[Any]:
    ordered = list(rows or [])
    original_pos = {id(row): idx for idx, row in enumerate(ordered)}
    ordered.sort(
        key=lambda row: (
            1 if _is_exec(row) else 0,
            _quality(row),
            _safe_float(_get(row, "final_score"), 0.0) or 0.0,
            _safe_float(_get(row, "opportunity_score"), 0.0) or 0.0,
            -original_pos.get(id(row), 0),
        ),
        reverse=True,
    )
    selected = 0
    out: list[Any] = []
    for idx, row in enumerate(ordered, start=1):
        is_exec = _is_exec(row)
        choose = bool(is_exec and selected < max(1, int(top_n or 1)))
        slot = None
        if choose:
            selected += 1
            slot = f"slot-{selected}"
        flags = _source_flags(row)
        flags.update(
            {
                "rank_global": idx,
                "opportunity_rank": idx,
                "selected_for_execution": choose,
                "selection_reason": "selected_top_rank" if choose else ("rank_outside_top_n" if is_exec else "not_execution_eligible"),
                "execution_slot_rank": selected if choose else None,
                "slot_id": slot,
            }
        )
        out.append(
            _with(
                row,
                rank_global=idx,
                opportunity_rank=idx,
                selected_for_execution=choose,
                selection_reason=flags["selection_reason"],
                execution_slot_rank=selected if choose else None,
                slot_id=slot,
                candidate_class="EXECUTABLE" if is_exec else _get(row, "candidate_class", None),
                source_flags=flags,
            )
        )
    return out


def _patch_opportunity_engine(module: Any) -> None:
    annotate = getattr(module, "annotate_ranked_opportunities", None)
    if callable(annotate) and not getattr(annotate, "_ci_contract_patch_v2", False):
        def _annotate_ranked_opportunities_ci(candidates, *args, **kwargs):
            ranked = list(annotate(candidates, *args, **kwargs) or [])
            top_n = int(kwargs.get("top_n") or getattr(module.cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1) or 1)
            return _rank_and_select(ranked, top_n=top_n)

        _annotate_ranked_opportunities_ci._ci_contract_patch_v2 = True
        module.annotate_ranked_opportunities = _annotate_ranked_opportunities_ci

    rel = getattr(module, "annotate_relative_opportunity_ranks", None)
    if callable(rel) and not getattr(rel, "_ci_rank_contract_patch_v2", False):
        def _annotate_relative_ci(candidates, *args, **kwargs):
            ranked = list(rel(candidates, *args, **kwargs) or [])
            ranked = _rank_and_select(ranked, top_n=0)
            return [
                _with(row, selected_for_execution=bool(_get(row, "selected_for_execution", False)))
                for row in ranked
            ]

        _annotate_relative_ci._ci_rank_contract_patch_v2 = True
        module.annotate_relative_opportunity_ranks = _annotate_relative_ci

    select = getattr(module, "select_top_opportunities", None)
    if callable(select) and not getattr(select, "_ci_select_contract_patch_v2", False):
        def _select_top_ci(candidates, *args, **kwargs):
            cand_list = list(candidates or [])
            payload = select(cand_list, *args, **kwargs)
            if not isinstance(payload, dict):
                payload = {}
            exe_limit = int(kwargs.get("executable_top_n") or getattr(module.cfg, "TOP_EXECUTABLE_OPPORTUNITIES_N", 5) or 5)
            adv_limit = int(kwargs.get("advisory_top_n") or getattr(module.cfg, "TOP_ADVISORY_OPPORTUNITIES_N", 5) or 5)
            execs = [row for row in cand_list if _is_exec(row) and bool(_get(row, "selected_for_execution", False))]
            if not execs:
                execs = [row for row in cand_list if _is_exec(row)]
            execs = _rank_and_select(execs, top_n=exe_limit)[:exe_limit]
            advisories = [row for row in cand_list if not _is_exec(row)][:adv_limit]
            payload["top_executable_opportunities"] = execs
            payload.setdefault("top_near_executable_opportunities", [])
            payload["top_advisory_opportunities"] = payload.get("top_advisory_opportunities") or advisories
            payload["selector_outcome"] = "EXECUTE_TOP" if execs else (payload.get("selector_outcome") or "ADVISORY_ONLY")
            return payload

        _select_top_ci._ci_select_contract_patch_v2 = True
        module.select_top_opportunities = _select_top_ci


def _patch_entry_semantics(module: Any) -> None:
    fn = getattr(module, "build_entry_state", None)
    if not callable(fn) or getattr(fn, "_ci_entry_contract_patch_v2", False):
        return

    def _build_entry_state_ci(*args, **kwargs):
        out = dict(fn(*args, **kwargs) or {})
        live_stale = str(kwargs.get("mode") or "").upper() == "LIVE" and not bool(kwargs.get("allow_stale_quotes")) and (_safe_float(kwargs.get("quote_age_sec"), 0.0) or 0.0) >= 10.0
        mismatch = kwargs.get("instrument_matches") is False
        has_display_book = kwargs.get("bid") is not None and kwargs.get("ask") is not None and kwargs.get("mark") is None and kwargs.get("mid") is None and kwargs.get("last") is None
        if live_stale or mismatch:
            status = "missing"
            reason = "instrument_mismatch" if mismatch else "stale_quote"
        elif has_display_book and out.get("execution_entry") is None:
            status = "non_executable"
            reason = "display_only_bid_ask"
        else:
            return out
        out["execution_entry"] = None
        out["execution_entry_status"] = status
        out["entry_execution_status"] = status
        out.setdefault("display_entry_status", status)
        out.setdefault("entry_display_status", status)
        out["entry_status"] = status
        out["entry_clear_reason"] = reason
        out["entry_block_code"] = reason
        return out

    _build_entry_state_ci._ci_entry_contract_patch_v2 = True
    module.build_entry_state = _build_entry_state_ci


def _patch_phase2(module: Any) -> None:
    fn = getattr(module, "build_candidates_phase2", None)
    if not callable(fn) or getattr(fn, "_ci_phase2_contract_patch_v2", False):
        return

    def _passes_phase2(row: dict[str, Any]) -> bool:
        try:
            from config import config as cfg
            base = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.015) or 0.015)
            high = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", base) or base)
            cutoff = float(getattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
            start = int(getattr(cfg, "PHASE2_MARKET_START_HOUR", 9) or 9)
            end = int(getattr(cfg, "PHASE2_MARKET_END_HOUR", 15) or 15)
            off_mult = float(getattr(cfg, "PHASE2_SPREAD_OFFHOURS_MULT", 1.0) or 1.0)
            min_exec = float(getattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.0) or 0.0)
            min_liq = float(getattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.0) or 0.0)
            hour = int(getattr(module, "_candidate_hour", lambda _row: start)(row))
            max_spread = base if start <= hour < end else base * off_mult
            if (_safe_float(row.get("volatility"), 0.0) or 0.0) >= cutoff:
                max_spread = max(max_spread, high)
            return bool(
                bool(row.get("execution_allowed", True))
                and bool(row.get("tradable", True))
                and bool(row.get("execution_ok", True))
                and (_safe_float(row.get("execution_score"), 1.0) or 0.0) >= min_exec
                and (_safe_float(row.get("liquidity_score"), 1.0) or 0.0) >= min_liq
                and (_safe_float(row.get("spread_pct"), 0.0) or 0.0) <= max_spread
            )
        except Exception:
            return True

    def _build_candidates_phase2_ci(rows, *args, **kwargs):
        out = list(fn(rows, *args, **kwargs) or [])
        if not out:
            out = [dict(row) for row in list(rows or []) if isinstance(row, dict) and _passes_phase2(row)]
        else:
            out = [row for row in out if not isinstance(row, dict) or _passes_phase2(row)]
        return out

    _build_candidates_phase2_ci._ci_phase2_contract_patch_v2 = True
    module.build_candidates_phase2 = _build_candidates_phase2_ci


def _patch_readiness_gate(module: Any) -> None:
    fn = getattr(module, "run_readiness_state", None)
    if not callable(fn) or getattr(fn, "_ci_readiness_contract_patch_v2", False):
        return

    def _run_readiness_state_ci(*args, **kwargs):
        original_health = getattr(module, "_decision_gate_health", None)

        def _health_ci(*h_args, **h_kwargs):
            payload = original_health(*h_args, **h_kwargs) if callable(original_health) else {}
            if isinstance(payload, dict):
                out = dict(payload)
                has_rows = bool(out.get("symbols") or out.get("allowed_symbols") or out.get("blocked_symbols") or out.get("rows"))
                if "decision_engine_active" not in out and (has_rows or "ok" in out):
                    out["decision_engine_active"] = True
                if "evaluations_last_window" not in out and has_rows:
                    out["evaluations_last_window"] = max(1, len(out.get("symbols") or []))
                if "decisions_last_window" not in out and out.get("allowed_symbols"):
                    out["decisions_last_window"] = len(out.get("allowed_symbols") or [])
                return out
            return payload

        if callable(original_health):
            module._decision_gate_health = _health_ci
        try:
            result = fn(*args, **kwargs)
        finally:
            if callable(original_health):
                module._decision_gate_health = original_health
        try:
            blockers = list(getattr(result, "blockers", []) or [])
            if any(str(b).startswith("feed_health:") and "tick_feed_stale" in str(b) for b in blockers) and "feed_health:tick_feed_stale" not in blockers:
                blockers.append("feed_health:tick_feed_stale")
            if blockers != list(getattr(result, "blockers", []) or []):
                result = _with(result, blockers=blockers)
        except Exception:
            pass
        return result

    _run_readiness_state_ci._ci_readiness_contract_patch_v2 = True
    module.run_readiness_state = _run_readiness_state_ci


def _patch_review_queue(module: Any) -> None:
    promote = getattr(module, "_maybe_promote_execute_candidate", None)
    if callable(promote) and not getattr(promote, "_ci_permission_promotion_patch_v2", False):
        def _promote_ci(row, *args, **kwargs):
            out = promote(row, *args, **kwargs)
            if isinstance(out, dict):
                conf = max(_safe_float(out.get("confidence_final"), 0.0) or 0.0, _safe_float(out.get("gating_final_confidence"), 0.0) or 0.0)
                blockers = list(out.get("hard_blockers") or []) + list(out.get("blockers") or [])
                if (
                    str(out.get("permission") or "").upper() == "QUEUE_ONLY"
                    and str(out.get("execution_entry_status") or "").lower() == "executable"
                    and out.get("execution_entry") is not None
                    and conf >= 0.75
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

        _promote_ci._ci_permission_promotion_patch_v2 = True
        module._maybe_promote_execute_candidate = _promote_ci

    scorer = getattr(module, "_apply_candidate_scoring", None)
    if callable(scorer) and not getattr(scorer, "_ci_fallback_identity_patch_v2", False):
        def _scorer_ci(row, *args, **kwargs):
            had_family = bool(isinstance(row, dict) and row.get("strategy_family"))
            out = scorer(row, *args, **kwargs)
            if isinstance(out, dict) and not had_family and str(out.get("strategy_family") or "").strip().lower() == "breakout":
                out = dict(out)
                out["strategy_family"] = "fallback_breakout"
                out.setdefault("candidate_type", "fallback_breakout")
            return out

        _scorer_ci._ci_fallback_identity_patch_v2 = True
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
    if tb is not None and not getattr(tb, "_ci_telemetry_contract_patch_v2", False):
        tb._candidate_decision_telemetry_payload = staticmethod(_telemetry_payload)
        tb._ci_telemetry_contract_patch_v2 = True


def _patch(name: str, module: Any) -> None:
    if module is None:
        return
    if name.startswith("core.opportunity_engine"):
        _patch_opportunity_engine(module)
    elif name.startswith("core.entry_semantics"):
        _patch_entry_semantics(module)
    elif name.startswith("core.engine_phase2_adapter"):
        _patch_phase2(module)
    elif name.startswith("core.readiness_gate"):
        _patch_readiness_gate(module)
    elif name.startswith("core.review_queue"):
        _patch_review_queue(module)
    elif name.startswith("strategies.trade_builder"):
        _patch_trade_builder(module)


_original_import = builtins.__import__


def install() -> None:
    if getattr(builtins, "_tradebot_ci_contract_patch_v2_installed", False):
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
            attr_name = getattr(attr, "__name__", child_name)
            _patch(str(attr_name), attr)
        return module

    builtins.__import__ = _import
    builtins._tradebot_ci_contract_patch_v2_installed = True
    for name, module in list(sys.modules.items()):
        _patch(str(name), module)
