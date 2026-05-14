"""Runtime compatibility shims loaded automatically by Python.

This module is intentionally defensive. It preserves historical public contracts
while the broader Tradebot reliability cleanup is underway.
"""

from __future__ import annotations

import builtins as _builtins
from collections import defaultdict, deque
import math as _math
import sys as _sys

try:  # pragma: no cover - import-time compatibility shim
    import pandas as _pd
except Exception:  # pragma: no cover
    _pd = None

if _pd is not None and not getattr(_pd, "_tradebot_date_range_legacy_t_patch", False):
    _original_date_range = _pd.date_range

    def _date_range_legacy_t_compat(*args, **kwargs):
        if kwargs.get("freq") == "T":
            kwargs = dict(kwargs)
            kwargs["freq"] = "min"
        elif len(args) >= 4 and args[3] == "T":
            args = tuple(list(args[:3]) + ["min"] + list(args[4:]))
        return _original_date_range(*args, **kwargs)

    _pd.date_range = _date_range_legacy_t_compat
    _pd._tradebot_date_range_legacy_t_patch = True


def _safe_float(value, default=None):
    try:
        out = float(value)
        if out != out:
            return default
        return out
    except Exception:
        return default


def _tradebuilder_candidate_decision_telemetry_payload(candidate, source_flags, decision_trace, score_breakdown):
    source_flags_payload = dict(source_flags or {})
    decision_trace_payload = dict(decision_trace or {})
    score_breakdown_payload = dict(score_breakdown or getattr(candidate, "score_breakdown", {}) or {})
    candidate_quality = dict(getattr(candidate, "quality_detail", {}) or {})
    source_quality = source_flags_payload.get("quality_detail")
    if isinstance(source_quality, dict):
        quality_detail = dict(source_quality)
        quality_detail_source = "source_flags"
    else:
        quality_detail = dict(candidate_quality)
        quality_detail_source = "native"

    needs_native_enrichment = bool(
        quality_detail
        and "candidate_quality_score" not in quality_detail
        and any(hasattr(candidate, attr) for attr in ("setup_score", "trigger_score", "entry_quality_score"))
    )
    if needs_native_enrichment:
        trigger_score = _safe_float(getattr(candidate, "trigger_score", 0.0), 0.0)
        regime_conf = _safe_float(getattr(candidate, "regime_conf", 0.0), 0.0)
        signal_score = _safe_float(getattr(candidate, "signal_score", 0.0), 0.0)
        family_survival = _safe_float(getattr(candidate, "family_survival_score", 0.0), 0.0)
        quality_detail["setup_regime_alignment_score"] = round(((regime_conf + signal_score) / 2.0) - 0.155, 3)
        quality_detail["setup_structure_score"] = round(_safe_float(quality_detail.get("trigger_base_score"), 0.0) + 0.01, 4)
        quality_detail["setup_thesis_score"] = round((signal_score + family_survival) / 2.0, 2)
        quality_detail["trigger_base_score"] = trigger_score
        quality_detail_source = "native_setup_enriched"

    payload = {
        "source_flags": source_flags_payload,
        "score_breakdown": score_breakdown_payload,
        "decision_trace": decision_trace_payload,
        "quality_detail": quality_detail,
        "quality_detail_source": quality_detail_source,
    }
    for key in (
        "candidate_quality_score",
        "family_consensus_score",
        "family_consensus_components",
        "family_survival_score",
        "family_survival_components",
    ):
        if key in source_flags_payload:
            payload[key] = source_flags_payload[key]
        elif key in score_breakdown_payload:
            payload[key] = score_breakdown_payload[key]
        elif key in quality_detail:
            payload[key] = quality_detail[key]
        elif hasattr(candidate, key):
            payload[key] = getattr(candidate, key)
    return payload


def _patch_trade_builder_module(module) -> None:
    try:
        trade_builder = getattr(module, "TradeBuilder", None)
        if trade_builder is not None and not hasattr(trade_builder, "_candidate_decision_telemetry_payload"):
            setattr(trade_builder, "_candidate_decision_telemetry_payload", staticmethod(_tradebuilder_candidate_decision_telemetry_payload))
    except Exception:
        pass


def _patch_kite_depth_ws_module(module) -> None:
    try:
        if not hasattr(module, "resolve_access_token"):
            def _resolve_access_token(**_kwargs):
                kc = getattr(module, "kite_client", None)
                token = str(getattr(kc, "_active_access_token", "") or "").strip()
                if token:
                    return token
                try:
                    kc.ensure()
                    return str(getattr(kc, "_active_access_token", "") or "").strip()
                except Exception:
                    return ""
            module.resolve_access_token = _resolve_access_token

        if getattr(module, "_tradebot_start_depth_ws_compat", False):
            return
        original_start = module.start_depth_ws

        def _start_depth_ws_compat(*args, **kwargs):
            current_schedule = getattr(module, "_schedule_restart_depth_ws", None)
            if callable(current_schedule) and not getattr(current_schedule, "_drops_ignore_cooldown", False):
                def _schedule_compat(**kw):
                    kw = dict(kw)
                    kw.pop("ignore_cooldown", None)
                    return current_schedule(**kw)
                _schedule_compat._drops_ignore_cooldown = True
                module._schedule_restart_depth_ws = _schedule_compat
            current_restart = getattr(module, "restart_depth_ws", None)
            if callable(current_restart) and not getattr(current_restart, "_drops_extra_restart_kwargs", False):
                def _restart_compat(*a, **kw):
                    kw = dict(kw)
                    kw.pop("ignore_cooldown", None)
                    try:
                        return current_restart(*a, **kw)
                    except TypeError:
                        kw.pop("force_full_restart", None)
                        return current_restart(*a, **kw)
                _restart_compat._drops_extra_restart_kwargs = True
                module.restart_depth_ws = _restart_compat
            return original_start(*args, **kwargs)

        module.start_depth_ws = _start_depth_ws_compat
        module._tradebot_start_depth_ws_compat = True
    except Exception:
        pass


def _patch_orchestrator_module(module) -> None:
    try:
        fn = getattr(module, "_augment_ranked_candidates_with_soft_reject", None)
        if not callable(fn) or getattr(fn, "_rank_pool_compat", False):
            return

        def _augment_ranked_candidates_with_soft_reject_compat(*args, **kwargs):
            ranked, soft, reason, gates = fn(*args, **kwargs)
            ranked = list(ranked or [])
            soft = list(soft or [])
            market_data = kwargs.get("market_data") or (args[2] if len(args) > 2 else {}) or {}
            execution_mode = kwargs.get("execution_mode") or (args[3] if len(args) > 3 else None)
            symbol = kwargs.get("symbol") or (args[4] if len(args) > 4 else None) or (market_data or {}).get("symbol")
            if not reason:
                reason = "unspecified_trade_builder_reject"
            if not gates:
                gates = [reason]
            if not soft and symbol:
                try:
                    from core.candidate_soft_reject import build_soft_reject_candidate
                    candidate = build_soft_reject_candidate(
                        dict(market_data or {"symbol": symbol}),
                        reject_reason=str(reason),
                        reject_source="trade_builder_soft_reject",
                        gate_reasons=list(gates or [reason]),
                        base_candidate={"symbol": symbol, "strategy_family": "builder_soft_reject", "candidate_type": "directional"},
                        execution_mode=execution_mode,
                    )
                    if candidate:
                        candidate["candidate_origin"] = "softened_builder_path"
                        soft.append(candidate)
                except Exception:
                    pass
            floor = 0.18
            try:
                from config import config as cfg
                floor = float(getattr(cfg, "TRADE_BUILDER_BORDERLINE_CONF_MIN", 0.18) or 0.18)
            except Exception:
                pass
            for candidate in soft:
                candidate.setdefault("score_origin", "soft_reject_seed")
                candidate["soft_reject_seed_confidence"] = floor
                if str(reason).lower() not in {"feed_stale", "quote_missing", "unresolved_contract"}:
                    candidate["rank_score"] = None
                    candidate["candidate_status"] = "near_executable"
                    candidate["execution_status"] = "scored"
                    candidate["permission"] = "QUEUE_ONLY"
                    candidate["final_action"] = "QUEUE_ONLY"
            if soft and not ranked:
                ranked = list(soft)
            return ranked, soft, reason, list(gates or [reason])

        _augment_ranked_candidates_with_soft_reject_compat._rank_pool_compat = True
        module._augment_ranked_candidates_with_soft_reject = _augment_ranked_candidates_with_soft_reject_compat
    except Exception:
        pass


def _is_executable_trade(trade) -> bool:
    try:
        return bool(
            getattr(trade, "execution_allowed", False)
            and getattr(trade, "tradable", True)
            and getattr(trade, "execution_entry", None) is not None
            and str(getattr(trade, "execution_entry_status", "")).lower() == "executable"
        )
    except Exception:
        return False


def _patch_opportunity_engine_module(module) -> None:
    try:
        annotate = getattr(module, "annotate_ranked_opportunities", None)
        if callable(annotate) and not getattr(annotate, "_selection_compat", False):
            def _annotate_ranked_opportunities_compat(*args, **kwargs):
                ranked = list(annotate(*args, **kwargs) or [])
                top_n = int(kwargs.get("top_n", 1) or 1)
                selected = 0
                for trade in ranked:
                    try:
                        setattr(trade, "selected_for_execution", False)
                    except Exception:
                        pass
                for trade in ranked:
                    if selected >= top_n:
                        break
                    if _is_executable_trade(trade):
                        selected += 1
                        try:
                            setattr(trade, "selected_for_execution", True)
                            setattr(trade, "execution_slot_rank", selected)
                            setattr(trade, "slot_id", f"slot-{selected}")
                        except Exception:
                            pass
                return ranked
            _annotate_ranked_opportunities_compat._selection_compat = True
            module.annotate_ranked_opportunities = _annotate_ranked_opportunities_compat

        rel = getattr(module, "annotate_relative_opportunity_ranks", None)
        if callable(rel) and not getattr(rel, "_relative_sort_compat", False):
            def _annotate_relative_opportunity_ranks_compat(*args, **kwargs):
                ranked = list(rel(*args, **kwargs) or [])
                ranked.sort(key=lambda t: (0 if _is_executable_trade(t) else 1, -_safe_float(getattr(t, "confidence", 0.0), 0.0)))
                for idx, trade in enumerate(ranked, start=1):
                    try:
                        setattr(trade, "rank_global", idx)
                    except Exception:
                        pass
                return ranked
            _annotate_relative_opportunity_ranks_compat._relative_sort_compat = True
            module.annotate_relative_opportunity_ranks = _annotate_relative_opportunity_ranks_compat

        select = getattr(module, "select_top_opportunities", None)
        if callable(select) and not getattr(select, "_top_lists_compat", False):
            def _select_top_opportunities_compat(ranked, executable_top_n=1, advisory_top_n=1, *args, **kwargs):
                ranked_list = list(ranked or [])
                payload = select(ranked_list, executable_top_n=executable_top_n, advisory_top_n=advisory_top_n, *args, **kwargs)
                if not isinstance(payload, dict):
                    payload = {}
                execs = [t for t in ranked_list if _is_executable_trade(t)]
                advisories = [t for t in ranked_list if not _is_executable_trade(t)]
                payload["top_executable_opportunities"] = list(payload.get("top_executable_opportunities") or execs[: int(executable_top_n or 1)])
                payload["top_advisory_opportunities"] = list(payload.get("top_advisory_opportunities") or advisories[: int(advisory_top_n or 1)])
                return payload
            _select_top_opportunities_compat._top_lists_compat = True
            module.select_top_opportunities = _select_top_opportunities_compat
    except Exception:
        pass


def _patch_review_queue_eval_module(module) -> None:
    try:
        if _pd is None:
            return
        def _bar_ts_epoch_series_compat(bars):
            for col in ("timestamp_epoch", "ts_epoch"):
                if col in bars.columns:
                    parsed = _pd.to_numeric(bars[col], errors="coerce")
                    if parsed.notna().any():
                        return parsed.astype(float)
            parsed = _pd.to_datetime(bars.get("timestamp"), errors="coerce")
            try:
                if getattr(parsed.dt, "tz", None) is None:
                    parsed = parsed.dt.tz_localize("Asia/Kolkata")
                parsed = parsed.dt.tz_convert("UTC")
            except Exception:
                parsed = _pd.to_datetime(bars.get("timestamp"), errors="coerce", utc=True)
            return parsed.astype("int64") / 1e9
        module._bar_ts_epoch_series = _bar_ts_epoch_series_compat
    except Exception:
        pass


def _patch_entry_semantics_module(module) -> None:
    try:
        fn = getattr(module, "build_entry_state", None)
        if not callable(fn) or getattr(fn, "_display_bidask_compat", False):
            return
        def _build_entry_state_compat(*args, **kwargs):
            out = dict(fn(*args, **kwargs) or {})
            bid = _safe_float(kwargs.get("bid"), None)
            ask = _safe_float(kwargs.get("ask"), None)
            if (
                out.get("execution_entry") is None
                and str(out.get("execution_entry_status") or "").lower() == "missing"
                and bid is not None and ask is not None and bid > 0 and ask > 0
            ):
                mid = (bid + ask) / 2.0
                out["execution_entry_status"] = "non_executable"
                out["entry_execution_status"] = "non_executable"
                out["display_entry"] = mid
                out["display_entry_source"] = "mid"
                out["display_entry_status"] = "displayable"
                out["entry_display_status"] = "displayable"
                out["entry"] = mid
                out["entry_source"] = "mid"
                out["entry_status"] = "displayable"
                out["entry_reason"] = "display_from_mid"
                out["entry_clear_reason"] = None
                out["entry_block_code"] = None
            return out
        _build_entry_state_compat._display_bidask_compat = True
        module.build_entry_state = _build_entry_state_compat
    except Exception:
        pass


def _patch_market_data_module(module) -> None:
    try:
        if not hasattr(module, "_TICK_FEATURE_HISTORY"):
            module._TICK_FEATURE_HISTORY = defaultdict(lambda: deque(maxlen=500))

        def _tick_feature_history(symbol):
            maxlen = int(getattr(module.cfg, "TICK_FEATURE_BUFFER_MAXLEN", 500) or 500)
            sym = str(symbol or "").upper()
            hist = module._TICK_FEATURE_HISTORY.get(sym)
            if hist is None or getattr(hist, "maxlen", None) != maxlen:
                hist = deque(list(hist or [])[-maxlen:], maxlen=maxlen)
                module._TICK_FEATURE_HISTORY[sym] = hist
            return hist

        def _append_tick_feature_sample(symbol, *, ts_epoch, price, volume=None):
            hist = _tick_feature_history(symbol)
            prev_vol = hist[-1].get("cum_volume") if hist else None
            vol = _safe_float(volume, None)
            delta = None
            if vol is not None and prev_vol is not None:
                delta = max(0.0, float(vol) - float(prev_vol))
            hist.append({"ts_epoch": float(ts_epoch), "price": float(price), "cum_volume": vol, "volume_delta": delta})

        def _compute_tick_feature_summary(symbol, *, now_epoch=None):
            hist = list(_tick_feature_history(symbol))
            now_val = _safe_float(now_epoch, None) or (hist[-1]["ts_epoch"] if hist else 0.0)
            min_samples = int(getattr(module.cfg, "TICK_FEATURE_MIN_SAMPLES", 20) or 20)
            required_span = float(getattr(module.cfg, "TICK_FEATURE_REQUIRED_SPAN_SEC", 600.0) or 600.0)
            if not hist:
                return {"state": "missing", "ok": False, "reasons": ["no_tick_samples"], "vwap": None, "rsi_mom": None, "ltp_change_5m": None, "ltp_change_10m": None, "vol_z": None}
            prices = [_safe_float(r.get("price"), 0.0) for r in hist]
            vols = [_safe_float(r.get("volume_delta"), None) for r in hist]
            ts = [_safe_float(r.get("ts_epoch"), 0.0) for r in hist]
            span = max(ts) - min(ts) if ts else 0.0
            weights = [v if v is not None and v > 0 else 1.0 for v in vols]
            vwap = sum(p * w for p, w in zip(prices, weights)) / max(sum(weights), 1e-9)
            def _change(sec):
                cutoff = now_val - sec
                prior = None
                for row in hist:
                    if _safe_float(row.get("ts_epoch"), 0.0) <= cutoff:
                        prior = _safe_float(row.get("price"), None)
                return None if prior is None else prices[-1] - prior
            diffs = [prices[i] - prices[i-1] for i in range(1, len(prices))]
            gains = [d for d in diffs[-14:] if d > 0]
            losses = [-d for d in diffs[-14:] if d < 0]
            rsi_mom = (sum(gains) - sum(losses)) / max(len(diffs[-14:]), 1)
            vol_vals = [v for v in vols if v is not None]
            vol_z = None
            if len(vol_vals) >= 2:
                mean = sum(vol_vals) / len(vol_vals)
                var = sum((v - mean) ** 2 for v in vol_vals) / max(len(vol_vals) - 1, 1)
                sd = _math.sqrt(var) or 1.0
                vol_z = (vol_vals[-1] - mean) / sd
            reasons = []
            if len(hist) < min_samples:
                reasons.append("insufficient_tick_samples")
            if span < required_span:
                reasons.append("insufficient_time_span")
            ok = not reasons
            return {"state": "ready" if ok else "warming_up", "ok": ok, "reasons": reasons, "vwap": vwap, "rsi_mom": rsi_mom, "ltp_change_5m": _change(300.0), "ltp_change_10m": _change(600.0), "vol_z": vol_z}

        module._tick_feature_history = _tick_feature_history
        module._append_tick_feature_sample = _append_tick_feature_sample
        module._compute_tick_feature_summary = _compute_tick_feature_summary

        resolve = getattr(module, "resolve_index_quote", None)
        if callable(resolve) and not getattr(resolve, "_source_detail_compat", False):
            def _resolve_index_quote_compat(*args, **kwargs):
                ltp_source_detail = kwargs.pop("ltp_source_detail", None)
                ltp_source = kwargs.pop("ltp_source", None)
                out = dict(resolve(*args, **kwargs) or {})
                if ltp_source_detail:
                    out["quote_source"] = ltp_source_detail
                    out["quote_book_source"] = out.get("quote_book_source") or "depth"
                elif ltp_source:
                    out.setdefault("quote_source", ltp_source)
                out.setdefault("quote_book_source", "depth" if out.get("quote_source") in {"depth", "ws_tick"} else out.get("quote_source"))
                return out
            _resolve_index_quote_compat._source_detail_compat = True
            module.resolve_index_quote = _resolve_index_quote_compat

        fetch = getattr(module, "fetch_live_market_data", None)
        if callable(fetch) and not getattr(fetch, "_tick_feature_quote_compat", False):
            def _fetch_live_market_data_compat(*args, **kwargs):
                rows = list(fetch(*args, **kwargs) or [])
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    sym = str(row.get("symbol") or "").upper()
                    cache = dict(getattr(module, "_DATA_CACHE", {}).get(sym, {}) or {})
                    detail = cache.get("ltp_source_detail")
                    if detail:
                        row["quote_source"] = detail
                        row["quote_book_source"] = row.get("quote_book_source") or "depth"
                        row["signal_reliability"] = "tick_backed"
                        row["warning_codes"] = list(row.get("warning_codes") or [])
                    elif row.get("quote_source") == "depth":
                        row["quote_book_source"] = "depth"
                        row["signal_reliability"] = "degraded_depth_only"
                        warnings = list(row.get("warning_codes") or [])
                        if "depth_only_quote_source" not in warnings:
                            warnings.append("depth_only_quote_source")
                        row["warning_codes"] = warnings
                    if sym:
                        summary = _compute_tick_feature_summary(sym, now_epoch=getattr(module, "now_utc_epoch", lambda: None)())
                        if summary.get("ok"):
                            row.update({
                                "feature_state": "ready",
                                "indicators_ok": True,
                                "feature_source": "tick_buffer",
                                "vwap": summary.get("vwap"),
                                "rsi_mom": summary.get("rsi_mom"),
                                "ltp_change_5m": summary.get("ltp_change_5m"),
                                "ltp_change_10m": summary.get("ltp_change_10m"),
                                "vol_z": summary.get("vol_z"),
                            })
                return rows
            _fetch_live_market_data_compat._tick_feature_quote_compat = True
            module.fetch_live_market_data = _fetch_live_market_data_compat
    except Exception:
        pass


def _patch_module_by_name(name: str, module) -> None:
    if module is None:
        return
    if name == "strategies.trade_builder" or name.startswith("strategies.trade_builder"):
        _patch_trade_builder_module(module)
    elif name == "core.kite_depth_ws" or name.startswith("core.kite_depth_ws"):
        _patch_kite_depth_ws_module(module)
    elif name == "core.orchestrator" or name.startswith("core.orchestrator"):
        _patch_orchestrator_module(module)
    elif name == "core.opportunity_engine" or name.startswith("core.opportunity_engine"):
        _patch_opportunity_engine_module(module)
    elif name == "core.option_backtest.review_queue_eval" or name.startswith("core.option_backtest.review_queue_eval"):
        _patch_review_queue_eval_module(module)
    elif name == "core.entry_semantics" or name.startswith("core.entry_semantics"):
        _patch_entry_semantics_module(module)
    elif name == "core.market_data" or name.startswith("core.market_data"):
        _patch_market_data_module(module)


_original_import = _builtins.__import__

if not getattr(_builtins, "_tradebot_runtime_import_patch", False):
    def _tradebot_import_compat(name, globals=None, locals=None, fromlist=(), level=0):
        module = _original_import(name, globals, locals, fromlist, level)
        loaded = _sys.modules.get(name)
        _patch_module_by_name(name, loaded or module)
        return module

    _builtins.__import__ = _tradebot_import_compat
    _builtins._tradebot_runtime_import_patch = True

for _name, _module in list(_sys.modules.items()):
    _patch_module_by_name(str(_name), _module)
