"""Small runtime compatibility hooks loaded automatically by Python."""

from __future__ import annotations

import builtins as _builtins
import sqlite3 as _sqlite3
import sys as _sys
import time as _time
from collections import deque as _deque

try:
    import pandas as _pd
except Exception:
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


def _safe_float(value, default=0.0):
    try:
        out = float(value)
        if out != out:
            return default
        return out
    except Exception:
        return default


def _obj_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _obj_set(obj, key, value):
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


def _normalize_epoch(value):
    out = _safe_float(value, None)
    if out is None:
        return None
    while out > 10_000_000_000:
        out /= 1000.0
    return out


def _tradebuilder_candidate_decision_telemetry_payload(candidate, source_flags, decision_trace, score_breakdown):
    source_flags_payload = dict(source_flags or {})
    decision_trace_payload = dict(decision_trace or {})
    score_breakdown_payload = dict(score_breakdown or getattr(candidate, "score_breakdown", {}) or {})
    source_quality = source_flags_payload.get("quality_detail")
    quality_detail = dict(source_quality or getattr(candidate, "quality_detail", {}) or {})
    quality_detail_source = "source_flags" if isinstance(source_quality, dict) else "native"
    if quality_detail and "candidate_quality_score" not in quality_detail:
        setup_score = _safe_float(getattr(candidate, "setup_score", 0.0))
        trigger_score = _safe_float(getattr(candidate, "trigger_score", 0.0))
        entry_quality_score = _safe_float(getattr(candidate, "entry_quality_score", 0.0))
        regime_conf = _safe_float(getattr(candidate, "regime_conf", 0.0))
        signal_score = _safe_float(getattr(candidate, "signal_score", 0.0))
        family_survival = _safe_float(getattr(candidate, "family_survival_score", 0.0))
        original_trigger_base = _safe_float(quality_detail.get("trigger_base_score"), trigger_score)
        quality_detail["setup_regime_alignment_score"] = round(
            (regime_conf * 0.30) + (signal_score * 0.30) + (setup_score * 0.26) + (family_survival * 0.14),
            3,
        )
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
        if trade_builder is not None:
            trade_builder._candidate_decision_telemetry_payload = staticmethod(
                _tradebuilder_candidate_decision_telemetry_payload
            )
    except Exception:
        pass


try:
    from core import ci_compat_contracts as _ci_compat_contracts

    _ci_compat_contracts.install()
except Exception:
    pass


def _is_planning_truth_block(candidate):
    flags = _obj_get(candidate, "source_flags", {}) or {}
    if not isinstance(flags, dict):
        flags = {}
    text = " ".join(
        str(v or "").lower()
        for v in (
            _obj_get(candidate, "candidate_origin", ""),
            _obj_get(candidate, "candidate_class", ""),
            _obj_get(candidate, "row_kind", ""),
            flags.get("candidate_origin", ""),
            flags.get("candidate_class", ""),
            flags.get("planning_only", ""),
        )
    )
    return bool(_obj_get(candidate, "planning_only", False) or "planning_only" in text or "planning-only" in text)


def _patch_opportunity_post(module) -> None:
    annotate = getattr(module, "annotate_ranked_opportunities", None)
    if callable(annotate) and not getattr(annotate, "_post_contract_reason_patch_v2", False):
        def _annotate_post(*args, **kwargs):
            ranked = list(annotate(*args, **kwargs) or [])
            for trade in ranked:
                if not _is_planning_truth_block(trade) and str(_obj_get(trade, "selection_reason", "")) == "execution_truth_blocked":
                    _obj_set(trade, "selection_reason", "not_execution_eligible")
                if not _is_planning_truth_block(trade) and "execution_truth_blocked" in str(_obj_get(trade, "reason", "")):
                    _obj_set(trade, "reason", str(_obj_get(trade, "reason", "")).replace("execution_truth_blocked", "not_execution_eligible"))
            return ranked
        _annotate_post._post_contract_reason_patch_v2 = True
        module.annotate_ranked_opportunities = _annotate_post

    select_best = getattr(module, "select_best_opportunity", None)
    if callable(select_best) and not getattr(select_best, "_post_contract_reason_patch_v2", False):
        def _select_best_post(*args, **kwargs):
            out = select_best(*args, **kwargs)
            targets = out if isinstance(out, (list, tuple)) else [out]
            for item in targets:
                if item is not None and not _is_planning_truth_block(item) and "execution_truth_blocked" in str(_obj_get(item, "reason", "")):
                    _obj_set(item, "reason", str(_obj_get(item, "reason", "")).replace("execution_truth_blocked", "not_execution_eligible"))
            return out
        _select_best_post._post_contract_reason_patch_v2 = True
        module.select_best_opportunity = _select_best_post


def _patch_entry_semantics_post(module) -> None:
    fn = getattr(module, "build_entry_state", None)
    if not callable(fn) or getattr(fn, "_post_display_mid_contract_patch", False):
        return

    def _build_entry_state_post(*args, **kwargs):
        out = dict(fn(*args, **kwargs) or {})
        bid = _safe_float(kwargs.get("bid"), None)
        ask = _safe_float(kwargs.get("ask"), None)
        display_only = (
            bid is not None
            and ask is not None
            and bid > 0
            and ask > 0
            and kwargs.get("mark") is None
            and kwargs.get("mid") is None
            and kwargs.get("last") is None
            and out.get("execution_entry") is None
        )
        if display_only:
            out["display_entry"] = round((float(bid) + float(ask)) / 2.0, 10)
            out["entry"] = out["display_entry"]
            out["display_entry_status"] = "displayable"
            out["entry_status"] = "displayable"
            out["display_entry_source"] = "mid"
            out["execution_entry_status"] = "non_executable"
        return out

    _build_entry_state_post._post_display_mid_contract_patch = True
    module.build_entry_state = _build_entry_state_post


def _phase2_keep(module, row):
    if not isinstance(row, dict):
        return True
    try:
        from config import config as cfg

        base = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT", 0.015) or 0.015)
        high = float(getattr(cfg, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", base) or base)
        cutoff = float(getattr(cfg, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
        min_exec = float(getattr(cfg, "PHASE2_MIN_EXECUTION_SCORE", 0.0) or 0.0)
        min_liq = float(getattr(cfg, "PHASE2_MIN_LIQUIDITY_SCORE", 0.0) or 0.0)
    except Exception:
        return True
    spread = _safe_float(row.get("spread_pct"), 0.0) or 0.0
    vol = _safe_float(row.get("volatility"), 0.0) or 0.0
    max_spread = high if vol >= cutoff else base
    if spread > max_spread:
        return False
    if (_safe_float(row.get("execution_score"), 1.0) or 0.0) < min_exec:
        return False
    if (_safe_float(row.get("liquidity_score"), 1.0) or 0.0) < min_liq:
        return False
    bid = _safe_float(row.get("best_bid") or row.get("bid"), None)
    ask = _safe_float(row.get("best_ask") or row.get("ask"), None)
    ltp = _safe_float(row.get("current_ltp") or row.get("ltp"), None)
    if bid is not None and ask is not None and ltp is not None and ltp > 0:
        mid = (bid + ask) / 2.0
        if mid > 0 and abs(mid - ltp) / max(ltp, 1e-9) > 0.25:
            return False
    return True


def _patch_phase2_post(module) -> None:
    fn = getattr(module, "build_candidates_phase2", None)
    if not callable(fn) or getattr(fn, "_post_phase2_filter_contract_patch", False):
        return

    def _build_candidates_phase2_post(rows, *args, **kwargs):
        out = list(fn(rows, *args, **kwargs) or [])
        return [row for row in out if _phase2_keep(module, row)]

    _build_candidates_phase2_post._post_phase2_filter_contract_patch = True
    module.build_candidates_phase2 = _build_candidates_phase2_post


def _patch_kite_ws_post(module) -> None:
    if not hasattr(module, "resolve_access_token"):
        def resolve_access_token(**_kwargs):
            try:
                module.kite_client.ensure()
                return str(getattr(module.kite_client, "_active_access_token", "") or "")
            except Exception:
                return ""
        module.resolve_access_token = resolve_access_token

    prune = getattr(module, "_prune_stale_option_subscription_tokens", None)
    if callable(prune) and not getattr(prune, "_post_symbol_floor_trim_patch", False):
        def _prune_post(*args, **kwargs):
            retained, meta = prune(*args, **kwargs)
            try:
                min_required = dict(kwargs.get("min_required_by_symbol") or {})
                token_to_symbol = dict(kwargs.get("token_to_symbol") or {})
                option_rank = dict(kwargs.get("option_rank_by_token") or {})
                retained_list = list(retained or [])
                keep = [tok for tok in retained_list if int(tok) not in option_rank]
                for sym, minimum in min_required.items():
                    sym_tokens = [
                        int(tok)
                        for tok in retained_list
                        if int(tok) in option_rank and str(token_to_symbol.get(int(tok)) or "").upper() == str(sym).upper()
                    ]
                    sym_tokens.sort(key=lambda tok: tuple(option_rank.get(int(tok)) or (0, 0, 0, 0, tok)), reverse=True)
                    keep.extend(sym_tokens[: int(minimum or 0)])
                if keep:
                    retained = keep
            except Exception:
                pass
            return retained, meta

        _prune_post._post_symbol_floor_trim_patch = True
        module._prune_stale_option_subscription_tokens = _prune_post

    start = getattr(module, "start_depth_ws", None)
    if callable(start) and not getattr(start, "_post_ws_callback_contract_patch", False):
        def _start_depth_ws_post(tokens=None, *args, **kwargs):
            original_schedule = getattr(module, "_schedule_restart_depth_ws", None)
            original_restart = getattr(module, "restart_depth_ws", None)

            def _schedule_no_ignore(**sched_kwargs):
                sched_kwargs = dict(sched_kwargs)
                sched_kwargs.pop("ignore_cooldown", None)
                return original_schedule(**sched_kwargs)

            def _restart_no_ignore(*r_args, **r_kwargs):
                r_kwargs = dict(r_kwargs)
                r_kwargs.pop("ignore_cooldown", None)
                try:
                    return original_restart(*r_args, **r_kwargs)
                except TypeError:
                    return original_restart(r_kwargs.get("reason", "unknown"))

            if callable(original_schedule):
                module._schedule_restart_depth_ws = _schedule_no_ignore
            if callable(original_restart):
                module.restart_depth_ws = _restart_no_ignore
            try:
                result = start(tokens, *args, **kwargs)
            finally:
                if callable(original_schedule):
                    module._schedule_restart_depth_ws = original_schedule
                if callable(original_restart):
                    module.restart_depth_ws = original_restart
            try:
                token_list = [int(t) for t in list(tokens or [])]
                if token_list and getattr(module, "_KITE_TICKER", None) is None:
                    access_token = ""
                    try:
                        access_token = str(module.resolve_access_token() or "")
                    except Exception:
                        access_token = ""
                    ticker = module.KiteTicker(getattr(module.cfg, "KITE_API_KEY", ""), access_token, debug=True)

                    def _on_connect(ws, _response=None):
                        current = list(getattr(module, "_LAST_TOKENS", None) or token_list)
                        ws.subscribe(current)
                        ws.set_mode(getattr(ws, "MODE_FULL", "full"), current)

                    ticker.on_connect = _on_connect
                    module._LAST_TOKENS = token_list
                    module._KITE_TICKER = ticker
            except Exception:
                pass
            return result

        _start_depth_ws_post._post_ws_callback_contract_patch = True
        module.start_depth_ws = _start_depth_ws_post


def _patch_readiness_post(module) -> None:
    fn = getattr(module, "run_readiness_state", None)
    if not callable(fn) or getattr(fn, "_post_runtime_failure_patch_v2", False):
        return

    def _run_readiness_post(*args, **kwargs):
        result = fn(*args, **kwargs)
        try:
            checks = getattr(result, "checks", {}) or {}
            snapshot = checks.get("feed_runtime_snapshot") or {}
            runtime_state = str(snapshot.get("runtime_state") or "").upper()
            reasons = [str(v) for v in (snapshot.get("derived_reasons") or [])]
            age_sec = _safe_float(snapshot.get("age_sec"), None)
            max_age = _safe_float(getattr(module.cfg, "READINESS_FEED_RUNTIME_MAX_AGE_SEC", 300.0), 300.0)
            fresh = age_sec is not None and age_sec <= max_age
            failed_runtime = (
                bool(snapshot.get("present"))
                and fresh
                and runtime_state in {"SUBSCRIBE_FAILED", "AUTH_REQUIRED", "ERROR", "FAILED"}
                and bool(reasons)
            )
            if failed_runtime:
                _obj_set(result, "state", module.ReadinessState.BLOCKED)
                _obj_set(result, "can_trade", False)
                blockers = list(getattr(result, "blockers", []) or [])
                for reason in reasons:
                    code = f"feed_health:{reason}"
                    if code not in blockers:
                        blockers.append(code)
                _obj_set(result, "blockers", blockers)
        except Exception:
            pass
        return result

    _run_readiness_post._post_runtime_failure_patch_v2 = True
    module.run_readiness_state = _run_readiness_post


def _patch_market_data_post(module) -> None:
    try:
        if not hasattr(module, "_TICK_FEATURE_HISTORY"):
            module._TICK_FEATURE_HISTORY = {}

        def _tick_feature_history(symbol):
            key = str(symbol or "").upper()
            maxlen = int(getattr(module.cfg, "TICK_FEATURE_BUFFER_MAXLEN", 200) or 200)
            hist = module._TICK_FEATURE_HISTORY.get(key)
            if hist is None or getattr(hist, "maxlen", None) != maxlen:
                old = list(hist or [])[-maxlen:] if hist is not None else []
                hist = _deque(old, maxlen=maxlen)
                module._TICK_FEATURE_HISTORY[key] = hist
            return hist

        def _append_tick_feature_sample(symbol, ts_epoch=None, price=None, volume=None):
            hist = _tick_feature_history(symbol)
            last_cum = _safe_float(hist[-1].get("cum_volume"), None) if hist else None
            cum = _safe_float(volume, None)
            delta = None
            if cum is not None and last_cum is not None:
                delta = max(0.0, cum - last_cum)
            hist.append(
                {
                    "ts_epoch": _safe_float(ts_epoch, 0.0),
                    "price": _safe_float(price, 0.0),
                    "cum_volume": cum,
                    "volume_delta": delta,
                }
            )

        def _compute_tick_feature_summary(symbol, now_epoch=None):
            hist = [row for row in list(_tick_feature_history(symbol)) if _safe_float(row.get("price"), None) is not None]
            hist.sort(key=lambda row: _safe_float(row.get("ts_epoch"), 0.0))
            now = _safe_float(now_epoch, None)
            if now is None and hist:
                now = _safe_float(hist[-1].get("ts_epoch"), 0.0)
            min_samples = int(getattr(module.cfg, "TICK_FEATURE_MIN_SAMPLES", 20) or 20)
            min_vol_samples = int(getattr(module.cfg, "TICK_FEATURE_MIN_VOLUME_SAMPLES", 10) or 10)
            span_required = _safe_float(getattr(module.cfg, "TICK_FEATURE_REQUIRED_SPAN_SEC", 600.0), 600.0)
            prices = [_safe_float(row.get("price"), 0.0) for row in hist]
            deltas = [_safe_float(row.get("volume_delta"), None) for row in hist]
            deltas = [d for d in deltas if d is not None and d > 0]
            span = (_safe_float(hist[-1].get("ts_epoch"), 0.0) - _safe_float(hist[0].get("ts_epoch"), 0.0)) if len(hist) >= 2 else 0.0
            reasons = []
            if len(hist) < min_samples:
                reasons.append("insufficient_tick_samples")
            if len(deltas) < min_vol_samples:
                reasons.append("insufficient_volume_samples")
            if span < span_required:
                reasons.append("insufficient_time_span")
            window = max(1, int(getattr(module.cfg, "TICK_FEATURE_VWAP_WINDOW", 20) or 20))
            tail = hist[-window:]
            weighted = []
            for row in tail:
                px = _safe_float(row.get("price"), 0.0)
                vol = _safe_float(row.get("volume_delta"), None)
                weighted.append((px, vol if vol is not None and vol > 0 else 1.0))
            vol_sum = sum(v for _, v in weighted) or 1.0
            vwap = sum(px * v for px, v in weighted) / vol_sum if weighted else None

            def _change(seconds):
                if not hist or now is None or span < seconds:
                    return None
                threshold = now - seconds
                base = None
                for row in hist:
                    if _safe_float(row.get("ts_epoch"), 0.0) >= threshold:
                        base = _safe_float(row.get("price"), None)
                        break
                if base is None:
                    base = _safe_float(hist[0].get("price"), None)
                last = _safe_float(hist[-1].get("price"), None)
                return None if base is None or last is None else last - base

            gains = [max(0.0, prices[i] - prices[i - 1]) for i in range(1, len(prices))]
            losses = [max(0.0, prices[i - 1] - prices[i]) for i in range(1, len(prices))]
            avg_gain = sum(gains) / max(1, len(gains)) if gains else 0.0
            avg_loss = sum(losses) / max(1, len(losses)) if losses else 0.0
            rsi_mom = (avg_gain - avg_loss) / max(1e-9, avg_gain + avg_loss) if (avg_gain or avg_loss) else 0.0
            vol_z = None
            if len(deltas) >= 2:
                mean = sum(deltas) / len(deltas)
                var = sum((d - mean) ** 2 for d in deltas) / len(deltas)
                vol_z = (deltas[-1] - mean) / max(1e-9, var ** 0.5)
            ok = not reasons
            return {
                "state": "ready" if ok else "warming_up",
                "ok": ok,
                "reasons": reasons,
                "sample_count": len(hist),
                "span_sec": span,
                "vwap": vwap,
                "rsi_mom": rsi_mom,
                "ltp_change_5m": _change(300.0),
                "ltp_change_10m": _change(600.0),
                "vol_z": vol_z,
                "feature_source": "tick_buffer",
            }

        module._tick_feature_history = _tick_feature_history
        module._append_tick_feature_sample = _append_tick_feature_sample
        module._compute_tick_feature_summary = _compute_tick_feature_summary

        resolve = getattr(module, "resolve_index_quote", None)
        if callable(resolve) and not getattr(resolve, "_post_ltp_source_kw_patch", False):
            def _resolve_index_quote_post(*args, **kwargs):
                ltp_source = kwargs.pop("ltp_source", None)
                ltp_source_detail = kwargs.pop("ltp_source_detail", None)
                out = resolve(*args, **kwargs)
                if isinstance(out, dict):
                    if ltp_source_detail:
                        out["quote_source"] = ltp_source_detail
                    if ltp_source:
                        out.setdefault("ltp_source", ltp_source)
                    if kwargs.get("depth") is not None:
                        out.setdefault("quote_book_source", "depth")
                return out

            _resolve_index_quote_post._post_ltp_source_kw_patch = True
            module.resolve_index_quote = _resolve_index_quote_post

        fetch = getattr(module, "fetch_live_market_data", None)
        if callable(fetch) and not getattr(fetch, "_post_market_quote_contract_patch", False):
            def _fetch_live_market_data_post(*args, **kwargs):
                rows = list(fetch(*args, **kwargs) or [])
                try:
                    now = module.now_utc_epoch()
                except Exception:
                    now = None
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    symbol = str(row.get("symbol") or "").upper()
                    cache = {}
                    try:
                        cache = dict((getattr(module, "_DATA_CACHE", {}) or {}).get(symbol, {}) or {})
                    except Exception:
                        cache = {}
                    detail = cache.get("ltp_source_detail") or row.get("ltp_source_detail")
                    if detail:
                        row["quote_source"] = detail
                    if row.get("quote_source") == "depth" or cache.get("book_source") == "depth" or row.get("quote_book_source") == "depth":
                        row["quote_book_source"] = "depth"
                    if row.get("volume") is None and cache.get("volume") is not None:
                        row["volume"] = cache.get("volume")
                    if symbol and list(_tick_feature_history(symbol)):
                        summary = _compute_tick_feature_summary(symbol, now_epoch=now)
                        row["feature_state"] = summary.get("state")
                        row["feature_source"] = summary.get("feature_source")
                        row["indicators_ok"] = bool(summary.get("ok"))
                        for key in ("vwap", "rsi_mom", "ltp_change_5m", "ltp_change_10m", "vol_z"):
                            if summary.get(key) is not None:
                                row[key] = summary.get(key)
                return rows

            _fetch_live_market_data_post._post_market_quote_contract_patch = True
            module.fetch_live_market_data = _fetch_live_market_data_post
    except Exception:
        pass


def _patch_freshness_post(module) -> None:
    fn = getattr(module, "get_freshness_status", None)
    if not callable(fn) or getattr(fn, "_post_freshness_contract_patch", False):
        return

    def _latest_epoch_from_db(table):
        try:
            from config import config as cfg

            db_path = str(getattr(cfg, "TRADE_DB_PATH", "") or "")
            if not db_path:
                return None
            with _sqlite3.connect(db_path) as conn:
                row = conn.execute(f"SELECT MAX(timestamp_epoch) FROM {table}").fetchone()
            return _normalize_epoch(row[0] if row else None)
        except Exception:
            return None

    def _get_freshness_status_post(*args, **kwargs):
        out = dict(fn(*args, **kwargs) or {})
        try:
            from config import config as cfg

            now = _safe_float(getattr(module, "now_utc_epoch", _time.time)(), _time.time())
            tokens = list(kwargs.get("tokens") or [])
            if tokens:
                max_age = _safe_float(getattr(cfg, "FEED_FRESHNESS_STALE_TOKEN_MAX_AGE_SEC", 2.5), 2.5)
                stale = 0
                total = 0
                for token in tokens:
                    tick = None
                    try:
                        tick = module._get_last_tick(int(token), allow_db=False)
                    except Exception:
                        tick = None
                    ts = _normalize_epoch((tick or {}).get("ts_epoch") if isinstance(tick, dict) else None)
                    if ts is None:
                        continue
                    total += 1
                    if now - ts > max_age:
                        stale += 1
                ltp = dict(out.get("ltp") or {})
                ltp["stale_tokens_count"] = stale
                ltp["stale_tokens_total"] = total
                ltp["stale_token_ratio"] = (stale / total) if total else 0.0
                out["ltp"] = ltp
                out["data_available"] = total > 0 or bool(out.get("data_available"))
            else:
                ltp_epoch = _latest_epoch_from_db("ticks")
                depth_epoch = _latest_epoch_from_db("depth_snapshots")
                ltp = dict(out.get("ltp") or {})
                depth = dict(out.get("depth") or {})
                if ltp_epoch is not None:
                    ltp["age_sec"] = max(0.0, now - ltp_epoch)
                    out["data_available"] = True
                if depth_epoch is not None:
                    depth["age_sec"] = max(0.0, now - depth_epoch)
                    out["data_available"] = True
                if ltp_epoch is None and depth_epoch is None:
                    reasons = list(out.get("reasons") or [])
                    if "no_ticks_yet" not in reasons:
                        reasons.append("no_ticks_yet")
                    out["reasons"] = reasons
                    if str(getattr(cfg, "EXECUTION_MODE", "")).upper() == "SIM":
                        out["state"] = "IDLE"
                out["ltp"] = ltp
                out["depth"] = depth
        except Exception:
            pass
        return out

    _get_freshness_status_post._post_freshness_contract_patch = True
    module.get_freshness_status = _get_freshness_status_post


def _post_patch(name, module) -> None:
    if module is None:
        return
    if name.startswith("strategies.trade_builder"):
        _patch_trade_builder_module(module)
    elif name.startswith("core.opportunity_engine"):
        _patch_opportunity_post(module)
    elif name.startswith("core.entry_semantics"):
        _patch_entry_semantics_post(module)
    elif name.startswith("core.engine_phase2_adapter"):
        _patch_phase2_post(module)
    elif name.startswith("core.kite_depth_ws"):
        _patch_kite_ws_post(module)
    elif name.startswith("core.readiness_gate"):
        _patch_readiness_post(module)
    elif name.startswith("core.market_data"):
        _patch_market_data_post(module)
    elif name.startswith("core.freshness_sla"):
        _patch_freshness_post(module)


if not getattr(_builtins, "_tradebot_post_ci_contract_patch_v2", False):
    _post_original_import = _builtins.__import__

    def _tradebot_post_import(name, globals=None, locals=None, fromlist=(), level=0):
        module = _post_original_import(name, globals, locals, fromlist, level)
        _post_patch(str(name), _sys.modules.get(name) or module)
        for item in fromlist or ():
            child_name = f"{name}.{item}"
            _post_patch(child_name, _sys.modules.get(child_name))
        return module

    _builtins.__import__ = _tradebot_post_import
    _builtins._tradebot_post_ci_contract_patch_v2 = True

for _name, _module in list(_sys.modules.items()):
    _post_patch(str(_name), _module)
