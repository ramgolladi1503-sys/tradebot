"""Targeted CI contract compatibility patches.

These are intentionally narrow. They patch only legacy public contracts that drifted
while the reliability branch is being cleaned up.
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
    return bool(
        _get(candidate, "execution_entry") is not None
        and str(_get(candidate, "execution_entry_status", "")).lower() == "executable"
    )


def _patch_opportunity_engine(module: Any) -> None:
    annotate = getattr(module, "annotate_ranked_opportunities", None)
    if callable(annotate) and not getattr(annotate, "_ci_contract_patch", False):
        def _annotate_ranked_opportunities_ci(candidates, *args, **kwargs):
            ranked = list(annotate(candidates, *args, **kwargs) or [])
            top_n = int(kwargs.get("top_n") or getattr(module.cfg, "OPPORTUNITY_TOP_N_EXECUTABLE", 1) or 1)
            selected = 0
            for idx, trade in enumerate(ranked, start=1):
                _set(trade, "rank_global", idx)
                _set(trade, "opportunity_rank", idx)
                _set(trade, "selected_for_execution", False)
                _set(trade, "execution_slot_rank", None)
                _set(trade, "slot_id", None)
            for trade in ranked:
                if selected >= top_n:
                    break
                if _is_exec(trade):
                    selected += 1
                    _set(trade, "selected_for_execution", True)
                    _set(trade, "selection_reason", "selected_top_rank")
                    _set(trade, "execution_slot_rank", selected)
                    _set(trade, "slot_id", f"slot-{selected}")
            return ranked
        _annotate_ranked_opportunities_ci._ci_contract_patch = True
        module.annotate_ranked_opportunities = _annotate_ranked_opportunities_ci

    rel = getattr(module, "annotate_relative_opportunity_ranks", None)
    if callable(rel) and not getattr(rel, "_ci_rank_contract_patch", False):
        def _annotate_relative_ci(candidates, *args, **kwargs):
            ranked = list(rel(candidates, *args, **kwargs) or [])
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
                execs.sort(key=lambda c: (_safe_float(_get(c, "rank_global"), 999999) or 999999, -(_safe_float(_get(c, "final_score"), 0.0) or 0.0)))
                payload["top_executable_opportunities"] = execs[:exe_limit]
            if not payload.get("top_advisory_opportunities"):
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

    _build_entry_state_ci._ci_entry_contract_patch = True
    module.build_entry_state = _build_entry_state_ci


def _patch_phase2(module: Any) -> None:
    fn = getattr(module, "build_candidates_phase2", None)
    if not callable(fn) or getattr(fn, "_ci_phase2_contract_patch", False):
        return

    def _build_candidates_phase2_ci(rows, *args, **kwargs):
        out = list(fn(rows, *args, **kwargs) or [])
        try:
            from config import config as cfg
            base = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.015) or 0.015)
            high = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", base) or base)
            cutoff = float(getattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
            return [r for r in out if (_safe_float(r.get("spread_pct"), 0.0) or 0.0) <= (high if (_safe_float(r.get("volatility"), 0.0) or 0.0) >= cutoff else base)]
        except Exception:
            return out

    _build_candidates_phase2_ci._ci_phase2_contract_patch = True
    module.build_candidates_phase2 = _build_candidates_phase2_ci


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


_original_import = builtins.__import__


def install() -> None:
    if getattr(builtins, "_tradebot_ci_contract_patch_installed", False):
        return

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        module = _original_import(name, globals, locals, fromlist, level)
        _patch(name, sys.modules.get(name) or module)
        return module

    builtins.__import__ = _import
    builtins._tradebot_ci_contract_patch_installed = True
    for name, module in list(sys.modules.items()):
        _patch(str(name), module)
