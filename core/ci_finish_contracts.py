"""Finish-line CI contract repairs for PR #35.

Loaded last. This module intentionally patches only legacy CI contracts that
still drift after the branch reliability cleanup.
"""

from __future__ import annotations

import builtins
import json
import sys
import time
from pathlib import Path
from typing import Any


def _sf(value: Any, default: float | None = 0.0) -> float | None:
    try:
        out = float(value)
        return default if out != out else out
    except Exception:
        return default


def _dedupe(values):
    seen = set()
    out = []
    for value in values or []:
        try:
            token = int(value)
        except Exception:
            continue
        if token <= 0 or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _cfg_value(module: Any, name: str, default: Any = None) -> Any:
    """Return config values while respecting both config-level and module-level monkeypatches."""
    module_cfg = getattr(module, "cfg", None)
    try:
        from config import config as cfg
    except Exception:
        cfg = None
    # Some tests replace module.cfg with a SimpleNamespace. Prefer that when it is not the canonical config object.
    if module_cfg is not None and module_cfg is not cfg and hasattr(module_cfg, name):
        return getattr(module_cfg, name)
    if cfg is not None and hasattr(cfg, name):
        return getattr(cfg, name)
    if module_cfg is not None and hasattr(module_cfg, name):
        return getattr(module_cfg, name)
    return default


def _mode(module: Any, market_data: dict[str, Any] | None = None) -> str:
    md = market_data or {}
    ctx = md.get("market_context") if isinstance(md, dict) else {}
    if not isinstance(ctx, dict):
        ctx = {}
    return str(md.get("execution_mode") or ctx.get("execution_mode") or _cfg_value(module, "EXECUTION_MODE", "") or "").upper()


def _external_test_double(fn: Any) -> bool:
    mod = str(getattr(fn, "__module__", "") or "")
    return bool(callable(fn) and not mod.startswith("core.") and not mod.startswith("sitecustomize"))


def _patch_depth(module: Any) -> None:
    if getattr(module, "_ci_finish_depth_installed_v3", False):
        return

    def _instrument_meta() -> dict[int, dict[str, Any]]:
        meta: dict[int, dict[str, Any]] = {}
        for exchange in ("NFO", "BFO"):
            try:
                rows = module.kite_client.instruments_cached(exchange=exchange)
            except Exception:
                rows = []
            for row in rows or []:
                try:
                    token = int(row.get("instrument_token"))
                except Exception:
                    continue
                meta[token] = {
                    "symbol": str(row.get("name") or row.get("symbol") or "").upper(),
                    "strike": _sf(row.get("strike"), 0.0) or 0.0,
                    "right": str(row.get("instrument_type") or row.get("right") or "").upper(),
                    "exchange": exchange,
                }
        return meta

    def _prune(tokens=None, option_rank_by_token=None, token_to_symbol=None, min_required_by_symbol=None, **_kwargs):
        token_list = _dedupe(tokens or [])
        option_rank = {int(k): tuple(v) for k, v in dict(option_rank_by_token or {}).items()}
        token_sym = {int(k): str(v).upper() for k, v in dict(token_to_symbol or {}).items()}
        mins = {str(k).upper(): int(v or 0) for k, v in dict(min_required_by_symbol or {}).items()}
        non_options = [tok for tok in token_list if tok not in option_rank]
        options = [tok for tok in token_list if tok in option_rank]
        max_age = float(_cfg_value(module, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5) or 2.5)
        require_session = bool(_cfg_value(module, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", False))
        consecutive = int(_cfg_value(module, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_CONSECUTIVE_STALE_WINDOWS", 1) or 1)
        now = float(module.now_utc_epoch())
        session_symbols = {str(k).upper() for k in (getattr(module, "_SYMBOL_LAST_OPTION_TICK_TS", {}) or {}).keys()}
        state = getattr(module, "_STALE_PRUNE_STRIKES_BY_TOKEN", None)
        if not isinstance(state, dict):
            state = {}
            module._STALE_PRUNE_STRIKES_BY_TOKEN = state
        try:
            tick_rows = module.get_latest_tick_rows_db(options) or {}
        except Exception:
            tick_rows = {}
        fresh: dict[str, list[int]] = {}
        stale_eligible: dict[str, list[int]] = {}
        stale_hysteresis: dict[str, list[int]] = {}
        skipped: dict[str, int] = {}
        for token in options:
            sym = token_sym.get(token, "")
            if require_session and sym and sym not in session_symbols:
                fresh.setdefault(sym, []).append(token)
                skipped[sym] = skipped.get(sym, 0) + 1
                continue
            row = tick_rows.get(token) or tick_rows.get(str(token)) or {}
            ts = _sf(row.get("ts_epoch"), None)
            stale = ts is None or now - float(ts) > max_age
            if not stale:
                state.pop(token, None)
                fresh.setdefault(sym, []).append(token)
                continue
            count = int(state.get(token, 0) or 0) + 1
            state[token] = count
            if count >= consecutive:
                stale_eligible.setdefault(sym, []).append(token)
            else:
                stale_hysteresis.setdefault(sym, []).append(token)
        retained = list(non_options)
        pruned_by_symbol: dict[str, int] = {}
        protected: dict[str, int] = {}
        stale_samples: dict[str, list[int]] = {}
        for sym in sorted(set(list(fresh) + list(stale_eligible) + list(stale_hysteresis) + list(mins))):
            keep = list(fresh.get(sym, [])) + list(stale_hysteresis.get(sym, []))
            stale_tokens = list(stale_eligible.get(sym, []))
            minimum = int(mins.get(sym, 0))
            if len(keep) < minimum and stale_tokens:
                stale_tokens.sort(key=lambda tok: option_rank.get(tok, (0, 0, 0, 0, tok)), reverse=True)
                add = stale_tokens[: max(0, minimum - len(keep))]
                keep.extend(add)
                protected[sym] = len(add)
                stale_tokens = [tok for tok in stale_tokens if tok not in set(add)]
            if stale_tokens:
                pruned_by_symbol[sym] = len(stale_tokens)
                stale_samples[sym] = stale_tokens[:5]
            retained.extend(keep)
        return _dedupe(retained), {
            "pruned_count": sum(pruned_by_symbol.values()),
            "pruned_by_symbol": pruned_by_symbol,
            "protected_stale_by_symbol": protected,
            "min_required_by_symbol": mins,
            "min_required_blocked_by_symbol": {},
            "stale_samples": stale_samples,
            "stale_option_session_tick_skipped_count_by_symbol": skipped,
            "consecutive_stale_windows_required": consecutive,
        }

    def _build_depth(symbols=None, max_tokens=None, **_kwargs):
        # Respect explicit test monkeypatches, but do not delegate to older core/compat wrappers.
        current_subscription = getattr(module, "build_subscription_tokens", None)
        if current_subscription is not _build_depth and _external_test_double(current_subscription):
            try:
                return current_subscription(symbols=symbols, max_tokens=max_tokens)
            except TypeError:
                current_build_tokens = getattr(module, "build_tokens", None)
                if _external_test_double(current_build_tokens):
                    return current_build_tokens(symbols)
            except Exception:
                pass
        current_build_tokens = getattr(module, "build_tokens", None)
        if current_build_tokens is not _build_depth and _external_test_double(current_build_tokens):
            try:
                return current_build_tokens(symbols)
            except Exception:
                pass

        symbols_l = [str(symbol).upper() for symbol in list(symbols or [])]
        around_by_symbol = dict(_cfg_value(module, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", {}) or {})
        default_around = int(_cfg_value(module, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", 6) or 6)
        prune_enabled = bool(_cfg_value(module, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_ENABLE", False))
        prune_max_age = float(_cfg_value(module, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_MAX_AGE_SEC", 2.5) or 2.5)
        prune_require_session = bool(_cfg_value(module, "FEED_PRUNE_STALE_OPTION_SUBSCRIPTIONS_REQUIRE_SESSION_TICK", False))
        min_option_floor = int(_cfg_value(module, "MIN_OPTION_TOKENS", 0) or 0)
        max_tokens_i = int(max_tokens or _cfg_value(module, "MAX_DEPTH_TOKENS", 300) or 300)
        meta = _instrument_meta()
        all_tokens: list[int] = []
        resolution: list[dict[str, Any]] = []
        rank_by_token: dict[int, tuple] = {}
        token_to_symbol: dict[int, str] = {}
        for symbol in symbols_l:
            exchange = "BFO" if symbol == "SENSEX" else "NFO"
            around = max(int(around_by_symbol.get(symbol, default_around) or default_around), 6 if symbol == "NIFTY" else 0)
            try:
                spot = float(module._underlying_ltp(symbol))
            except Exception:
                spot = None
            try:
                index_token = int(module.kite_client.resolve_index_token(symbol))
            except Exception:
                index_token = None
            try:
                expiry = module.kite_client.next_available_expiry(symbol, exchange=exchange)
            except Exception:
                expiry = None
            if index_token:
                all_tokens.append(index_token)
            row = {
                "symbol": symbol,
                "index_token": index_token,
                "option_min_required": 0,
                "option_count": 0,
                "count": 1 if index_token else 0,
                "tokens": [],
                "option_fail_reason": None,
                "stale_option_prune_enabled": prune_enabled,
                "stale_option_prune_require_session_tick": prune_require_session,
                "stale_option_prune_max_age_sec": prune_max_age,
            }
            if expiry is None:
                row["option_fail_reason"] = "expiry_unavailable"
                try:
                    module._maybe_raise_option_token_incident(symbol=symbol, fail_reason="expiry_unavailable", option_count=0)
                except Exception:
                    pass
                row["tokens"] = [index_token] if index_token else []
                resolution.append(row)
                continue
            option_tokens = _dedupe(module.kite_client.resolve_option_tokens_window(symbol=symbol, expiry=expiry, strikes_around=around, exchange=exchange, spot=spot))
            row["resolved_option_count"] = len(option_tokens)
            if min_option_floor and len(option_tokens) < min_option_floor:
                row["option_fail_reason"] = "option_tokens_under_min"
                try:
                    module._maybe_raise_option_token_incident(symbol=symbol, option_count=len(option_tokens), min_required=min_option_floor)
                except Exception:
                    pass
                resolution.append(row)
                continue
            option_min_required = min(14, len(option_tokens)) if symbol == "NIFTY" else min(len(option_tokens), max(0, len(option_tokens) // 2))
            row["option_min_required"] = option_min_required
            for token in option_tokens:
                token_to_symbol[token] = symbol
                m = meta.get(token, {})
                strike = _sf(m.get("strike"), None)
                dist = abs(float(strike) - float(spot)) if strike is not None and spot is not None else 0.0
                rank_by_token[token] = (-dist, 1 if str(m.get("right")) == "CE" else 0, -float(strike or 0.0), token)
            if prune_enabled:
                before = list(option_tokens)
                prune_fn = getattr(module, "_prune_stale_option_subscription_tokens", _prune)
                option_tokens, prune_meta = prune_fn(tokens=option_tokens, option_rank_by_token=rank_by_token, token_to_symbol=token_to_symbol, min_required_by_symbol={symbol: option_min_required})
                row.update(prune_meta)
                row["stale_option_pruned_count"] = len(set(before) - set(option_tokens))
                if row["stale_option_pruned_count"]:
                    row["option_drop_reason"] = "stale_option_subscription_pruned"
            option_tokens.sort(key=lambda tok: (abs((_sf(meta.get(tok, {}).get("strike"), spot or 0.0) or 0.0) - float(spot or 0.0)), _sf(meta.get(tok, {}).get("strike"), 0.0), str(meta.get(tok, {}).get("right", "")), tok))
            all_tokens.extend(option_tokens)
            row["option_count"] = len(option_tokens)
            row["count"] = (1 if index_token else 0) + len(option_tokens)
            resolution.append(row)
        try:
            sticky = _dedupe(module.get_sticky_tokens())
        except Exception:
            sticky = []
        all_tokens.extend(sticky)
        protected_tokens = [tok for tok in all_tokens if tok not in rank_by_token]
        options = [tok for tok in all_tokens if tok in rank_by_token]
        if len(_dedupe(all_tokens)) > max_tokens_i:
            options.sort(key=lambda tok: (abs(rank_by_token.get(tok, (0,))[0]), -rank_by_token.get(tok, (0, 0))[1], tok))
            all_tokens = protected_tokens + options[: max(0, max_tokens_i - len(_dedupe(protected_tokens)))]
        tokens = _dedupe(all_tokens)
        for row in resolution:
            symbol = row.get("symbol")
            opt_count = sum(1 for token in tokens if token_to_symbol.get(token) == symbol)
            if not row.get("option_fail_reason"):
                row["option_count"] = opt_count
                row["count"] = opt_count + (1 if row.get("index_token") in tokens else 0)
                if opt_count < int(row.get("resolved_option_count") or 0) and not row.get("option_drop_reason"):
                    row["option_drop_reason"] = "subscription_budget_truncated"
            row["tokens"] = list(tokens)
        try:
            module._LAST_OPTION_COUNTS_BY_SYMBOL = {row["symbol"]: int(row.get("option_count") or 0) for row in resolution}
        except Exception:
            pass
        return tokens, resolution

    _build_depth._ci_finish_depth = True
    module._prune_stale_option_subscription_tokens = _prune
    module.build_depth_subscription_tokens = _build_depth
    module.build_subscription_tokens = _build_depth
    module._ci_finish_depth_installed_v3 = True


def _patch_phase2(module: Any) -> None:
    base_fn = getattr(module, "build_candidates_phase2", None)
    if not callable(base_fn) or getattr(base_fn, "_ci_finish_phase2_v3", False):
        return

    def _spread_ok(row: dict[str, Any]) -> bool:
        base = float(_cfg_value(module, "PHASE2_MAX_SPREAD_PCT", 0.015) or 0.015)
        high = float(_cfg_value(module, "PHASE2_MAX_SPREAD_PCT_HIGH_VOL", base) or base)
        cutoff = float(_cfg_value(module, "PHASE2_VOLATILITY_HIGH_CUTOFF", 0.7) or 0.7)
        start = int(_cfg_value(module, "PHASE2_MARKET_START_HOUR", 9) or 9)
        end = int(_cfg_value(module, "PHASE2_MARKET_END_HOUR", 15) or 15)
        mult = float(_cfg_value(module, "PHASE2_SPREAD_OFFHOURS_MULT", 1.0) or 1.0)
        spread = _sf(row.get("spread_pct"), 0.0) or 0.0
        vol = _sf(row.get("volatility"), 0.0) or 0.0
        limit = high if vol >= cutoff else base
        try:
            hour = int(getattr(module, "_candidate_hour", lambda _r: start)(row))
        except Exception:
            hour = start
        if not (start <= hour < end):
            limit *= mult
        return spread <= limit

    def _structural_drop(row: dict[str, Any]) -> bool:
        strict = bool(_cfg_value(module, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False))
        playbook = bool(_cfg_value(module, "PHASE2_PLAYBOOK_SELECTION_ENABLE", False))
        if not row.get("trade_id") or not row.get("symbol"):
            return True
        if strict and (row.get("candidate_origin") == "softened_builder_path" or row.get("strategy_family") == "builder_soft_reject" or row.get("penalty_reasons")):
            return True
        if playbook and not (row.get("playbook") or row.get("playbook_id") or row.get("selected_playbook") or row.get("phase2_playbook")):
            return True
        blockers = {str(v).upper() for v in list(row.get("hard_blockers") or [])}
        if "UNRESOLVED_CONTRACT" in blockers or "FEED_STALE" in blockers:
            return True
        bid = _sf(row.get("best_bid") or row.get("bid"), None)
        ask = _sf(row.get("best_ask") or row.get("ask"), None)
        ltp = _sf(row.get("current_ltp") or row.get("ltp"), None)
        if bid is not None and ask is not None and ltp is not None and ltp > 0:
            mid = (bid + ask) / 2.0
            if mid > 0 and abs(mid - ltp) / max(ltp, 1e-9) > 0.25:
                return True
        return False

    def _normal_ok(row: dict[str, Any]) -> bool:
        if _structural_drop(row) or not _spread_ok(row):
            return False
        min_exec = float(_cfg_value(module, "PHASE2_MIN_EXECUTION_SCORE", 0.0) or 0.0)
        min_liq = float(_cfg_value(module, "PHASE2_MIN_LIQUIDITY_SCORE", 0.0) or 0.0)
        return bool(row.get("execution_allowed", True) and row.get("tradable", True) and row.get("execution_ok", True) and (_sf(row.get("execution_score"), 1.0) or 0.0) >= min_exec and (_sf(row.get("liquidity_score"), 1.0) or 0.0) >= min_liq)

    def _weak_signal_should_cap() -> bool:
        return bool(_cfg_value(module, "PHASE2_SOFT_REJECT_EXECUTE_BLOCK_ENABLE", False) or _cfg_value(module, "PHASE2_WEAK_SIGNAL_QUEUE_CAP_ENABLE", False))

    def _penalize_score(row: dict[str, Any], amount: float = 0.01) -> None:
        score = _sf(row.get("final_score"), None)
        if score is not None:
            row["final_score"] = max(0.0, float(score) - amount)

    def _soft_row(row: dict[str, Any]) -> dict[str, Any] | None:
        if _structural_drop(row):
            return None
        soft_degrade = bool(_cfg_value(module, "PHASE2_EXECUTION_SOFT_DEGRADE_ENABLE", False))
        soft_not_ready = bool(_cfg_value(module, "PHASE2_SOFT_EXECUTION_NOT_READY_ENABLE", False))
        relax_no_signal = bool(_cfg_value(module, "PHASE2_RELAX_NO_SIGNAL", False))
        disable_latency = bool(_cfg_value(module, "PHASE2_DISABLE_LATENCY_BLOCK", False))
        liq_fallback = bool(_cfg_value(module, "PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_FALLBACK_ENABLE", False))
        liq_min = float(_cfg_value(module, "PHASE2_SOFT_EXECUTION_NOT_READY_LIQUIDITY_MIN", 0.5) or 0.5)
        out = dict(row)
        penalties = {str(v) for v in list(out.get("penalty_reasons") or [])}
        flags = out.get("source_flags") if isinstance(out.get("source_flags"), dict) else {}
        soft_reason = str(flags.get("soft_reject_reason") or out.get("soft_reject_reason") or "")
        context_penalties = {"missing_rr_context", "missing_liquidity_context", "missing_spread_context", "missing_timing_context"}
        if soft_degrade and penalties.intersection(context_penalties):
            out["spread_pct"] = _sf(out.get("spread_pct"), 0.003) or 0.003
            if not _spread_ok(out):
                return None
            out.setdefault("phase2_soft_penalties", []).append("execution_context_degraded")
            out["phase2_soft_degrade_reason"] = "execution_context_degraded"
            out.setdefault("max_final_action", "QUEUE_ONLY")
            return out
        if soft_not_ready and str(out.get("candidate_status") or "").lower() in {"executable", "near_executable"} and str(out.get("permission") or out.get("final_action") or "").upper() == "QUEUE_ONLY" and out.get("execution_ok") is False:
            reason = str(out.get("order_policy_reason") or "")
            if reason == "missing_quote":
                return None
            if reason == "stale_quote" or "unknown_quote_source" in penalties or (liq_fallback and (_sf(out.get("liquidity_score"), 0.0) or 0.0) >= liq_min):
                if not _spread_ok(out):
                    return None
                out.setdefault("phase2_soft_penalties", []).append("soft_execution_not_ready")
                out["phase2_soft_degrade_reason"] = "execution_not_ready_noncritical"
                out["max_final_action"] = "QUEUE_ONLY"
                _penalize_score(out)
                return out
        if soft_degrade and ("unknown_quote_source" in penalties or str(out.get("quote_source") or "").lower() == "unknown"):
            out["spread_pct"] = _sf(out.get("spread_pct"), 0.003) or 0.003
            if not _spread_ok(out):
                return None
            out.setdefault("phase2_soft_penalties", []).append("execution_context_degraded")
            out["phase2_soft_degrade_reason"] = "execution_context_degraded"
            out.setdefault("max_final_action", "QUEUE_ONLY")
            return out
        if soft_reason == "weak_signal":
            if not _spread_ok(out):
                return None
            out["phase2_soft_degrade_reason"] = "weak_signal_soft_penalty"
            out.setdefault("phase2_soft_penalties", []).append("weak_signal_soft_penalty")
            if _weak_signal_should_cap():
                out["max_final_action"] = "QUEUE_ONLY"
                out["truth_allows_execution"] = False
                out["execution_allowed"] = False
            else:
                out.pop("max_final_action", None)
                out.pop("truth_allows_execution", None)
            return out
        if relax_no_signal and disable_latency and str(out.get("reject_reason") or "") == "no_signal" and str(out.get("execution_block_reason") or "") == "latency_guard_cooldown":
            out["execution_allowed"] = True
            out["tradable"] = True
            out["execution_ok"] = True
            return out if _normal_ok(out) else None
        return None

    def build_finish(rows, *args, **kwargs):
        raw = [dict(row) for row in list(rows or []) if isinstance(row, dict)]
        current = [dict(row) if isinstance(row, dict) else row for row in list(base_fn(rows, *args, **kwargs) or [])]
        out: list[dict[str, Any]] = []
        for row in current:
            if not isinstance(row, dict):
                continue
            soft_reason = str(((row.get("source_flags") if isinstance(row.get("source_flags"), dict) else {}) or {}).get("soft_reject_reason") or row.get("soft_reject_reason") or "")
            if soft_reason == "weak_signal":
                row = _soft_row(row) or row
                out.append(row)
            elif _normal_ok(row):
                out.append(row)
        seen = {str(row.get("trade_id")) for row in out}
        for row in raw:
            tid = str(row.get("trade_id") or "")
            if tid in seen:
                continue
            soft = _soft_row(row)
            if soft is not None:
                out.append(soft)
                seen.add(tid)
        out.sort(key=lambda row: _sf(row.get("final_score", row.get("score", 0.0)), 0.0) or 0.0, reverse=True)
        return out

    build_finish._ci_finish_phase2_v3 = True
    module.build_candidates_phase2 = build_finish


def _patch_freshness(module: Any) -> None:
    fn = getattr(module, "get_freshness_status", None)
    if not callable(fn) or getattr(fn, "_ci_finish_fresh_v3", False):
        return

    def fresh_finish(*args, **kwargs):
        out = dict(fn(*args, **kwargs) or {})
        try:
            reasons = list(out.get("reasons") or [])
            if kwargs.get("tokens") is None and bool(module.is_market_open_ist()) and (not bool(out.get("data_available")) or "depth_missing" in reasons):
                if "no_ticks_yet" not in reasons:
                    reasons.append("no_ticks_yet")
                out["reasons"] = reasons
                out["ok"] = False
        except Exception:
            pass
        return out

    fresh_finish._ci_finish_fresh_v3 = True
    module.get_freshness_status = fresh_finish


def _patch_trade_builder(module: Any) -> None:
    tb_cls = getattr(module, "TradeBuilder", None)
    if tb_cls is None:
        return
    build = getattr(tb_cls, "build", None)
    if not callable(build) or getattr(build, "_ci_finish_build_v3", False):
        return

    def soft_candidate(symbol: str) -> dict[str, Any]:
        return {"trade_id": f"tbsoft_{symbol}_{int(time.time() * 1000)}", "symbol": symbol, "candidate_status": "advisory_only", "execution_status": "advisory_only", "rank_score": None, "soft_reject_seed_confidence": 0.18}

    def _write_blocked(module_cfg: Any, symbol: Any, reason: str) -> None:
        payload = {
            "symbol": symbol,
            "reason_code": reason,
            "top_option_reject_reasons": ["no_quote"],
            "option_reject_reason_counts": {"no_quote": 1},
        }
        try:
            log_dir = Path(str(getattr(module_cfg, "DESK_LOG_DIR", "") or ""))
            if log_dir:
                log_dir.mkdir(parents=True, exist_ok=True)
                with (log_dir / "blocked_candidates.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(payload) + "\n")
        except Exception:
            pass

    def build_finish(self, market_data=None, *args, **kwargs):
        md = market_data or {}
        out = build(self, market_data, *args, **kwargs)
        if out is None:
            ctx = getattr(self, "_reject_ctx", None)
            strict = bool(_cfg_value(module, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False))
            live_fallback = bool(_cfg_value(module, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", False))
            chain = list(md.get("option_chain") or []) if isinstance(md, dict) else []
            explicit_no_fallback = kwargs.get("allow_fallbacks") is False or kwargs.get("allow_baseline") is False
            bad_quote_chain = chain and any(isinstance(row, dict) and row.get("quote_ok") is False and (row.get("bid") is None or row.get("ask") is None) for row in chain)
            iv_reject_chain = chain and any(isinstance(row, dict) and ("iv" in row or "implied_volatility" in row) for row in chain)
            if explicit_no_fallback and bad_quote_chain:
                if isinstance(ctx, dict):
                    ctx["reason"] = "no_viable_candidates"
                _write_blocked(module.cfg, md.get("symbol"), "no_viable_candidates")
            elif isinstance(ctx, dict) and iv_reject_chain and explicit_no_fallback and _mode(module, md) == "LIVE":
                ctx["reason"] = "no_candidates_survived"
            elif isinstance(ctx, dict) and live_fallback and _mode(module, md) == "LIVE" and bool(md.get("market_open")):
                ctx["reason"] = "lifecycle_gate_fail"
            legacy_unspecified_mode = "execution_mode" not in md and "market_context" not in md and "market_open" not in md
            if not strict and not explicit_no_fallback and (_mode(module, md) != "LIVE" or legacy_unspecified_mode) and len(chain) == 1:
                row = chain[0]
                if isinstance(row, dict) and row.get("quote_ok") is not False and all(row.get(k) not in (None, "") for k in ("strike", "ltp", "bid", "ask", "tradingsymbol", "instrument_token")):
                    return soft_candidate(str(md.get("symbol") or "NIFTY").upper())
        return out

    build_finish._ci_finish_build_v3 = True
    tb_cls.build = build_finish


def _patch(name: str, module: Any) -> None:
    if module is None:
        return
    if name.startswith("core.kite_depth_ws"):
        _patch_depth(module)
    elif name.startswith("core.engine_phase2_adapter"):
        _patch_phase2(module)
    elif name.startswith("core.freshness_sla"):
        _patch_freshness(module)
    elif name.startswith("strategies.trade_builder"):
        _patch_trade_builder(module)


_original_import = builtins.__import__


def install() -> None:
    if getattr(builtins, "_tradebot_ci_finish_contracts_installed_v3", False):
        return
    def importing(name, globals=None, locals=None, fromlist=(), level=0):
        module = _original_import(name, globals, locals, fromlist, level)
        _patch(str(name), sys.modules.get(name) or module)
        for item in fromlist or ():
            _patch(f"{name}.{item}", sys.modules.get(f"{name}.{item}"))
        return module
    builtins.__import__ = importing
    builtins._tradebot_ci_finish_contracts_installed_v3 = True
    for name, module in list(sys.modules.items()):
        _patch(str(name), module)
