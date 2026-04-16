import json
import logging
import time
from pathlib import Path
from core.paths import logs_dir

from config import config as cfg
from core.market_context import derive_market_context
from core.reject_logger import append_reject_reasons
from core.time_utils import compute_age_sec, now_ist, now_utc_epoch
from core.trade_schema import build_instrument_id, validate_trade_identity
from core.trade_ticket import TradeTicket

logger = logging.getLogger(__name__)


def _trade_attr(trade, name: str, default=None):
    if isinstance(trade, dict):
        return trade.get(name, default)
    return getattr(trade, name, default)


def build_decision_event(orch, trade, market_data: dict, gatekeeper_allowed: bool, veto_reasons=None, pilot_allowed=None, pilot_reasons=None):
    now_text = now_ist().isoformat()
    now_epoch = float(now_utc_epoch())
    veto_reasons = list(veto_reasons or [])
    pilot_reasons = pilot_reasons or []
    opt = orch._match_option_snapshot(trade, market_data) if trade else None
    bid = (opt or {}).get("bid") if opt else market_data.get("bid")
    ask = (opt or {}).get("ask") if opt else market_data.get("ask")
    spread_pct = None
    if bid and ask:
        try:
            spread_pct = (ask - bid) / max((opt or {}).get("ltp") or market_data.get("ltp") or 1, 1)
        except Exception:
            spread_pct = None
    quote_ts = (opt or {}).get("quote_ts") if opt else None
    if quote_ts is None:
        quote_ts = market_data.get("quote_ts")
    quote_age_sec = orch._quote_age_sec(quote_ts)
    if quote_age_sec is None:
        quote_age_sec = market_data.get("quote_age_sec")
    quote_ts_epoch = orch._quote_ts_epoch(quote_ts)
    if quote_ts_epoch is None:
        quote_ts_epoch = market_data.get("quote_ts_epoch")
    feed_health = market_data.get("feed_health") if isinstance(market_data.get("feed_health"), dict) else {}
    if quote_ts_epoch is None:
        for candidate_epoch in (
            market_data.get("timestamp_epoch"),
            market_data.get("latest_option_tick_ts"),
            market_data.get("last_tick_ts"),
            market_data.get("last_ws_tick_epoch"),
            market_data.get("feed_timestamp_epoch"),
            market_data.get("ts_epoch"),
            feed_health.get("latest_option_tick_ts"),
            feed_health.get("last_tick_epoch"),
            feed_health.get("ts_epoch"),
        ):
            normalized_epoch = orch._quote_ts_epoch(candidate_epoch)
            if normalized_epoch is not None:
                quote_ts_epoch = normalized_epoch
                break
    if quote_age_sec is None and quote_ts_epoch is not None:
        quote_age_sec = compute_age_sec(quote_ts_epoch, now_epoch)
    if quote_age_sec is None:
        for candidate_age in (
            market_data.get("latest_option_tick_age_sec"),
            market_data.get("last_tick_age_sec"),
            feed_health.get("option_quote_age_sec"),
            feed_health.get("ltp_age_sec"),
        ):
            try:
                if candidate_age is None:
                    continue
                quote_age_sec = float(candidate_age)
                break
            except Exception:
                continue
    bid_qty = (opt or {}).get("bid_qty") or (opt or {}).get("bidQty")
    ask_qty = (opt or {}).get("ask_qty") or (opt or {}).get("askQty")
    depth_imb = market_data.get("depth_imbalance")
    if depth_imb is None and opt:
        depth_imb = opt.get("depth_imbalance")
    lineage = market_data.get("model_lineage", {}) or {}
    instrument_type = None
    right = None
    expiry = None
    strike = None
    decision_snapshot = None
    snapshot_id = None
    if trade:
        instrument_type = getattr(trade, "instrument_type", None) or getattr(trade, "instrument", None)
        right = getattr(trade, "right", None) or getattr(trade, "option_type", None)
        expiry = getattr(trade, "expiry", None)
        strike = getattr(trade, "strike", None)
        snapshot_id = getattr(trade, "snapshot_id", None)
        source_flags = getattr(trade, "source_flags", None)
        if isinstance(source_flags, dict):
            snap = source_flags.get("decision_snapshot")
            if isinstance(snap, dict):
                decision_snapshot = dict(snap)
            if not snapshot_id:
                snapshot_id = source_flags.get("decision_snapshot_id")
    symbol = (_trade_attr(trade, "symbol") if trade else market_data.get("symbol"))
    trade_instrument_id = getattr(trade, "instrument_id", None) if trade else None
    instrument_id = trade_instrument_id
    if instrument_id is None and trade and instrument_type:
        instrument_id = build_instrument_id(_trade_attr(trade, "symbol"), instrument_type, expiry, strike, right)
    if instrument_id is None:
        fb_symbol = str(symbol or "UNKNOWN")
        fb_instrument_type = str(instrument_type or market_data.get("instrument") or "UNKNOWN")
        fb_expiry = str(expiry or market_data.get("expiry") or "NA")
        fb_strike = str(strike if strike not in (None, "") else market_data.get("strike") or "NA")
        fb_right = str(right or market_data.get("option_type") or "NA")
        instrument_id = f"MISSING_CONTRACT::{fb_symbol}:{fb_instrument_type}:{fb_expiry}:{fb_strike}:{fb_right}"
    ctx_payload = {}
    raw_ctx = market_data.get("market_context")
    if isinstance(raw_ctx, dict):
        nested_ctx = raw_ctx.get("market_context")
        if isinstance(nested_ctx, dict):
            ctx_payload.update(dict(nested_ctx))
        ctx_payload.update(dict(raw_ctx))
    if "execution_mode" not in ctx_payload:
        raw_exec_mode = market_data.get("execution_mode")
        if raw_exec_mode is not None:
            ctx_payload["execution_mode"] = raw_exec_mode
    if "market_open" not in ctx_payload and ("market_open" in market_data):
        ctx_payload["market_open"] = market_data.get("market_open")
    if "segment" not in ctx_payload:
        raw_segment = market_data.get("segment")
        if raw_segment is not None:
            ctx_payload["segment"] = raw_segment
    market_ctx = derive_market_context(ctx_payload or {"execution_mode": getattr(cfg, "EXECUTION_MODE", "SIM")})

    def _safe_float(value):
        try:
            if value is None:
                return None
            return float(value)
        except Exception:
            return None

    _quote_age = orch._quote_age_sec(market_data.get("quote_ts"))
    event = {
        "trade_id": _trade_attr(trade, "trade_id") if trade else None,
        "ts": now_text,
        "symbol": symbol,
        "mode": market_ctx.mode,
        "market_open": bool(market_ctx.is_market_open),
        "planning_only": bool(market_ctx.planning_only),
        "allow_stale_quotes": bool(market_ctx.allow_stale_quotes),
        "require_live_quotes": bool(market_ctx.require_live_quotes),
        "strategy_id": _trade_attr(trade, "strategy") if trade else None,
        "regime": market_data.get("regime") or (_trade_attr(trade, "regime") if trade else None),
        "regime_probs": market_data.get("regime_probs"),
        "shock_score": market_data.get("shock_score"),
        "side": _trade_attr(trade, "side") if trade else None,
        "instrument": _trade_attr(trade, "instrument") if trade else None,
        "instrument_id": instrument_id,
        "strike": strike,
        "expiry": expiry,
        "expiry_date": getattr(trade, "expiry_date", None) if trade else (market_data.get("expiry_date") or expiry),
        "tradingsymbol": getattr(trade, "tradingsymbol", None) if trade else (opt or {}).get("tradingsymbol"),
        "option_type": getattr(trade, "option_type", None) if trade else None,
        "right": right,
        "instrument_type": instrument_type,
        "underlying": _trade_attr(trade, "symbol") if trade else None,
        "underlying_spot": (getattr(trade, "underlying_spot", None) if trade else None) or market_data.get("underlying_spot") or market_data.get("ltp"),
        "spot_source": (getattr(trade, "spot_source", None) if trade else None)
        or market_data.get("spot_source")
        or market_data.get("ltp_source")
        or market_data.get("index_quote_source"),
        "option_ltp_source": (getattr(trade, "option_ltp_source", None) if trade else None)
        or (opt or {}).get("option_ltp_source")
        or (opt or {}).get("quote_source"),
        "snapshot_id": snapshot_id,
        "chain_source": (getattr(trade, "chain_source", None) if trade else None)
        or market_data.get("chain_source")
        or (opt or {}).get("chain_source"),
        "qty_lots": getattr(trade, "qty_lots", None) if trade else None,
        "qty_units": getattr(trade, "qty_units", None) if trade else None,
        "validity_sec": getattr(trade, "validity_sec", None) if trade else None,
        "dte": orch._calc_dte(getattr(trade, "expiry", None)) if trade else None,
        "expiry_bucket": market_data.get("expiry_type") or market_data.get("expiry_bucket"),
        "score_0_100": getattr(trade, "trade_score", None) if trade else None,
        "xgb_proba": _trade_attr(trade, "confidence") if trade and _trade_attr(trade, "model_type", None) == "xgb" else None,
        "deep_proba": _trade_attr(trade, "confidence") if trade and _trade_attr(trade, "model_type", None) == "deep" else None,
        "micro_proba": (opt or {}).get("micro_pred"),
        "ensemble_proba": getattr(trade, "alpha_confidence", None) if trade else None,
        "ensemble_uncertainty": getattr(trade, "alpha_uncertainty", None) if trade else None,
        "champion_proba": getattr(trade, "confidence", None) if trade else None,
        "challenger_proba": getattr(trade, "shadow_confidence", None) if trade else None,
        "champion_model_id": getattr(trade, "model_version", None) if trade else None,
        "challenger_model_id": getattr(trade, "shadow_model_version", None) if trade else None,
        "signal_v1": (
            getattr(trade, "signal_v1", None)
            if trade and isinstance(getattr(trade, "signal_v1", None), dict)
            else {
                "confidence": getattr(trade, "confidence", None) if trade else None,
                "features": {
                    "pattern_flags": list(getattr(trade, "pattern_flags", []) or []) if trade else [],
                    "rank_score": getattr(trade, "trade_score", None) if trade else None,
                },
                "direction": str(getattr(trade, "side", "") or "") if trade else "",
            }
        ),
        "execution_v1": (
            getattr(trade, "execution_v1", None)
            if trade and isinstance(getattr(trade, "execution_v1", None), dict)
            else {
                "can_execute": bool(gatekeeper_allowed and not bool(veto_reasons)),
                "execution_score": (
                    (_safe_float(getattr(trade, "global_confidence", getattr(trade, "confidence", 0.0))) or 0.0)
                    if trade
                    else 0.0
                ),
                "execution_reject_reason": (
                    str(veto_reasons[0]) if veto_reasons else None
                ),
            }
        ),
        "model_id": lineage.get("model_id") or (getattr(trade, "model_version", None) if trade else None),
        "dataset_hash": lineage.get("dataset_hash"),
        "feature_hash": lineage.get("feature_hash"),
        "bid": bid,
        "ask": ask,
        "spread_pct": spread_pct,
        "bid_qty": bid_qty,
        "ask_qty": ask_qty,
        "depth_imbalance": depth_imb,
        "quote_age_sec": quote_age_sec,
        "quote_ts_epoch": quote_ts_epoch,
        "depth_age_sec": market_data.get("depth_age_sec"),
        "feed_health": feed_health or market_data.get("feed_health"),
        "time_sanity": market_data.get("time_sanity"),
        "fill_prob_est": getattr(cfg, "EXEC_FILL_PROB", None),
        "portfolio_equity": orch.portfolio.get("capital"),
        "equity": orch.portfolio.get("capital"),
        "equity_high": orch.portfolio.get("equity_high"),
        "daily_pnl": orch.portfolio.get("daily_pnl", orch.portfolio.get("daily_profit", 0.0) + orch.portfolio.get("daily_loss", 0.0)),
        "daily_pnl_pct": orch.portfolio.get("daily_pnl_pct"),
        "drawdown_pct": orch.risk_state.daily_max_drawdown if hasattr(orch.risk_state, "daily_max_drawdown") else None,
        "loss_streak": orch.loss_streak.get(_trade_attr(trade, "symbol"), 0) if trade else 0,
        "open_risk": orch.portfolio.get("open_risk", orch._open_risk()),
        "open_risk_pct": orch.portfolio.get("open_risk_pct"),
        "delta_exposure": None,
        "gamma_exposure": None,
        "vega_exposure": None,
        "gatekeeper_allowed": 1 if gatekeeper_allowed else 0,
        "veto_reasons": veto_reasons,
        "risk_allowed": None,
        "exec_guard_allowed": None,
        "pilot_allowed": pilot_allowed,
        "pilot_reasons": pilot_reasons,
        "action_size_multiplier": None,
        "filled_bool": None,
        "fill_price": None,
        "time_to_fill": None,
        "slippage_vs_mid": None,
        "pnl_horizon_5m": None,
        "pnl_horizon_15m": None,
        "mae_15m": None,
        "mfe_15m": None,
    }
    if trade and getattr(trade, "tradable", True) is False:
        for reason in list(getattr(trade, "tradable_reasons_blocking", []) or []):
            if reason not in veto_reasons:
                veto_reasons.append(reason)
        event["veto_reasons"] = veto_reasons
    if trade and str(instrument_type or "").upper() == "OPT":
        if (getattr(trade, "instrument_id", None) is None) or (not getattr(trade, "expiry_date", None)):
            if "unresolved_contract" not in veto_reasons:
                veto_reasons.append("unresolved_contract")
            event["veto_reasons"] = veto_reasons
    if event.get("instrument_id") is None and trade:
        ok, _reason = validate_trade_identity(
            _trade_attr(trade, "symbol"),
            instrument_type,
            expiry,
            strike,
            right,
        )
        if not ok:
            veto_reasons.append("missing_contract_fields")
            event["veto_reasons"] = veto_reasons
        event["instrument_id"] = None
    if event.get("quote_age_sec") is None:
        event["quote_age_sec"] = market_data.get("quote_age_sec")
    if event.get("quote_age_sec") is None:
        is_global_event = str(symbol or "").strip().upper() == "GLOBAL"
        logger.warning(
            "DECISION_FEED_EVIDENCE symbol=%s is_global=%s timestamp_epoch=%s latest_option_tick_ts=%s latest_option_tick_age_sec=%s ws_connected=%s subscribed_option_tokens_count=%s quote_ts_epoch=%s quote_age_sec=%s veto_reasons=%s",
            symbol,
            bool(is_global_event),
            market_data.get("timestamp_epoch"),
            market_data.get("latest_option_tick_ts"),
            market_data.get("latest_option_tick_age_sec"),
            market_data.get("ws_connected", feed_health.get("ws_connected")),
            market_data.get("subscribed_option_tokens_count", feed_health.get("subscribed_option_tokens_count")),
            quote_ts_epoch,
            event.get("quote_age_sec"),
            list(veto_reasons),
        )
        event["quote_age_sec"] = -1.0
        if not is_global_event and "epoch_missing" not in veto_reasons:
            veto_reasons.append("epoch_missing")
        event["veto_reasons"] = veto_reasons
    if decision_snapshot is not None:
        event["decision_snapshot"] = decision_snapshot
    return event


def log_identity_error(_orch, trade, extra: dict | None = None) -> None:
    try:
        path = logs_dir() / "trade_identity_errors.jsonl"
        path.parent.mkdir(exist_ok=True)

        def _get(obj, key):
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        payload = {
            "ts_epoch": now_utc_epoch(),
            "trade_id": _get(trade, "trade_id"),
            "symbol": _get(trade, "symbol"),
            "instrument_type": _get(trade, "instrument_type") or _get(trade, "instrument"),
            "expiry": _get(trade, "expiry"),
            "strike": _get(trade, "strike"),
            "right": _get(trade, "right") or _get(trade, "option_type"),
        }
        if extra:
            payload.update(extra)
        reason_code = payload.get("reason_code") or payload.get("reason")
        if reason_code is not None:
            reason_text = str(reason_code).strip()
            if reason_text:
                payload["reason_code"] = reason_text
                payload["reason"] = str(payload.get("reason") or reason_text)
        with path.open("a") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


def log_decision_safe(orch, event: dict, trade=None, log_decision_fn=None):
    event = dict(event or {})
    veto_reasons = [str(x).strip() for x in (event.get("veto_reasons") or []) if str(x).strip()]
    try:
        gatekeeper_allowed = int(event.get("gatekeeper_allowed") or 0)
    except Exception:
        gatekeeper_allowed = 0
    if gatekeeper_allowed == 1 and event.get("trade_id"):
        try:
            from core.storage import emit_candidate_created_event

            emit_candidate_created_event(
                symbol=event.get("symbol"),
                strategy=event.get("strategy_id"),
                mode=event.get("mode") or getattr(cfg, "EXECUTION_MODE", "SIM"),
                confidence=event.get("champion_proba"),
                instrument={
                    "symbol": event.get("symbol"),
                    "instrument_id": event.get("instrument_id"),
                    "instrument_token": event.get("instrument_token"),
                    "tradingsymbol": event.get("tradingsymbol"),
                },
                features_summary={
                    "score_0_100": event.get("score_0_100"),
                    "spread_pct": event.get("spread_pct"),
                    "quote_age_sec": event.get("quote_age_sec"),
                    "regime": event.get("regime"),
                },
            )
        except Exception:
            pass
    facts = event.get("facts") if isinstance(event.get("facts"), dict) else {}
    tele = event.get("strategy_telemetry") if isinstance(event.get("strategy_telemetry"), dict) else None
    if tele is None:
        try:
            tele = (facts or {}).get("strategy_telemetry")
        except Exception:
            tele = None
    tele_compact = None
    if isinstance(tele, dict):
        tele_compact = {
            "qual_fail_codes": tele.get("qual_fail_codes"),
            "picked_candidate": tele.get("picked_candidate"),
            "precondition_failures": tele.get("precondition_failures"),
            "qual_fail_reasons_raw": tele.get("qual_fail_reasons_raw"),
        }
        ac = tele.get("all_candidates")
        if isinstance(ac, list) and len(ac) <= 10:
            tele_compact["all_candidates"] = ac
    if veto_reasons:
        blockers = event.get("decision_blockers")
        if not isinstance(blockers, list):
            blockers = list(veto_reasons or [])

        event_telemetry = event.get("strategy_telemetry")
        if not isinstance(event_telemetry, dict):
            event_telemetry = None

        reject_extra = {
            "trade_id": event.get("trade_id"),
            "gatekeeper_allowed": event.get("gatekeeper_allowed"),
            "decision_stage": event.get("decision_stage") or "decision:event",
            "decision_explain": event.get("decision_explain"),
            "decision_blockers": blockers,
            "strategy_telemetry": event_telemetry,
            "facts": (event.get("facts") if isinstance(event.get("facts"), dict) else None),
        }
        append_reject_reasons(
            symbol=event.get("symbol"),
            strategy=event.get("strategy_id"),
            reasons=veto_reasons,
            mode=(event.get("mode") or getattr(cfg, "EXECUTION_MODE", "SIM")),
            source="decision_event",
            extra=reject_extra,
        )
    if event.get("instrument_id") is None:
        symbol = str(event.get("symbol") or (getattr(trade, "symbol", None) if trade is not None else None) or "UNKNOWN")
        instrument_type = str(
            event.get("instrument_type")
            or (getattr(trade, "instrument_type", None) if trade is not None else None)
            or (getattr(trade, "instrument", None) if trade is not None else None)
            or event.get("instrument")
            or "UNKNOWN"
        )
        expiry = str(event.get("expiry") or (getattr(trade, "expiry", None) if trade is not None else None) or "NA")
        strike = str(event.get("strike") or (getattr(trade, "strike", None) if trade is not None else None) or "NA")
        right = str(
            event.get("right")
            or (getattr(trade, "right", None) if trade is not None else None)
            or event.get("option_type")
            or (getattr(trade, "option_type", None) if trade is not None else None)
            or "NA"
        )
        fallback_instrument_id = f"MISSING_CONTRACT::{symbol}:{instrument_type}:{expiry}:{strike}:{right}"
        event["instrument_id"] = fallback_instrument_id
        if "missing_contract_fields" not in veto_reasons:
            veto_reasons.append("missing_contract_fields")
            event["veto_reasons"] = veto_reasons
        if trade is not None:
            log_identity_error(orch, trade or event, {"reason": "missing_contract_fields"})
        reject_extra = {
            "trade_id": event.get("trade_id"),
            "fallback_instrument_id": fallback_instrument_id,
            "decision_stage": "decision:gatekeeper",
            "decision_explain": "Strategy decision pipeline rejected the candidate set",
            "decision_blockers": ["missing_contract_fields"],
            "strategy_telemetry": tele_compact,
            "facts": facts,
        }
        append_reject_reasons(
            symbol=event.get("symbol"),
            strategy=event.get("strategy_id"),
            reasons=["missing_contract_fields"],
            mode=(event.get("mode") or getattr(cfg, "EXECUTION_MODE", "SIM")),
            source="decision",
            extra=reject_extra,
        )
    if log_decision_fn is None:
        raise RuntimeError("log_decision_fn is required")
    return log_decision_fn(event)


def instrument_id(_orch, trade):
    if not trade:
        return None
    try:
        instrument_type = getattr(trade, "instrument_type", None) or getattr(trade, "instrument", None)
        right = getattr(trade, "right", None) or getattr(trade, "option_type", None)
        expiry = getattr(trade, "expiry", None)
        strike = getattr(trade, "strike", None)
        return build_instrument_id(_trade_attr(trade, "symbol"), instrument_type, expiry, strike, right)
    except Exception:
        return None


def build_trade_ticket(orch, trade, _market_data: dict) -> TradeTicket:
    validity = int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180))
    reason_codes = []
    regime_value = _trade_attr(trade, "regime", None)
    strategy_value = _trade_attr(trade, "strategy", None)
    if regime_value:
        reason_codes.append(f"regime:{regime_value}")
    if strategy_value:
        reason_codes.append(f"strategy:{strategy_value}")
    for blocked_reason in list(_trade_attr(trade, "tradable_reasons_blocking", []) or []):
        reason_codes.append(f"block:{blocked_reason}")
    guardrails = []
    max_spread = float(getattr(cfg, "MAX_SPREAD_PCT", 0.03))
    guardrails.append(f"spread>{max_spread:.2%}")
    max_age = float(getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0))
    guardrails.append(f"quote_age>{max_age:.1f}s")
    ticket = TradeTicket.from_trade(
        trade,
        validity_sec=validity,
        reason_codes=reason_codes,
        guardrails=guardrails,
        desk_id=getattr(cfg, "DESK_ID", "DEFAULT"),
    )
    meta = orch.trade_meta.get(_trade_attr(trade, "trade_id", ""), {}) or {}
    if meta:
        ticket.trailing_enabled = bool(meta.get("trailing_enabled", ticket.trailing_enabled))
        ticket.trailing_method = meta.get("trailing_method", ticket.trailing_method)
        ticket.trailing_atr_mult = meta.get("trailing_atr_mult", ticket.trailing_atr_mult)
        ticket.trail_stop_init = meta.get("trail_stop_init", ticket.trail_stop_init)
        ticket.trail_stop_last = meta.get("trail_stop", ticket.trail_stop_last)
        ticket.trail_updates = int(meta.get("trail_updates", ticket.trail_updates or 0))
    return ticket


def log_meta_shadow(orch, trade, market_data):
    if not orch.meta_model:
        return
    try:
        strategy_name = _trade_attr(trade, "strategy", None)
        stats = dict(orch.strategy_tracker.stats.get(strategy_name, {}) or {})
        decay = orch.strategy_tracker.decay_probs.get(strategy_name, {})
        if decay:
            stats.update(decay)
        try:
            baseline_weight = float(orch.strategy_allocator._weight(strategy_name))
        except Exception:
            baseline_weight = 1.0
        suggestion = orch.meta_model.suggest(
            strategy_name,
            _trade_attr(trade, "model_type", None),
            market_data,
            stats,
        )
        payload = {
            "ts_epoch": now_utc_epoch(),
            "symbol": _trade_attr(trade, "symbol"),
            "strategy": strategy_name,
            "trade_id": _trade_attr(trade, "trade_id"),
            "baseline_weight": baseline_weight,
            "suggested_weight": suggestion.get("suggested_weight"),
            "weight_delta": (suggestion.get("suggested_weight") or 0) - baseline_weight,
            "baseline_predictor": suggestion.get("baseline_predictor"),
            "suggested_predictor": suggestion.get("suggested_predictor"),
            "primary_regime": suggestion.get("primary_regime"),
            "regime_probs": suggestion.get("regime_probs"),
            "decay_prob": suggestion.get("decay_prob"),
            "exec_quality": suggestion.get("exec_quality"),
            "shadow_only": bool(getattr(cfg, "META_MODEL_SHADOW_ONLY", True)),
        }
        orch.meta_model.log_shadow(payload)
    except Exception:
        pass
    sym = market_data.get("symbol")
    decision_id = f"{sym}-DECISION-{int(time.time()*1000)}"
    return {
        "trade_id": decision_id,
        "ts": now_ist().isoformat(),
        "symbol": sym,
        "strategy_id": None,
        "regime": market_data.get("regime"),
        "regime_probs": market_data.get("regime_probs"),
        "shock_score": market_data.get("shock_score"),
        "side": None,
        "instrument": None,
        "dte": None,
        "expiry_bucket": market_data.get("expiry_type") or market_data.get("expiry_bucket"),
        "score_0_100": None,
        "xgb_proba": None,
        "deep_proba": None,
        "micro_proba": None,
        "ensemble_proba": None,
        "ensemble_uncertainty": None,
        "champion_proba": None,
        "challenger_proba": None,
        "champion_model_id": None,
        "challenger_model_id": None,
        "bid": market_data.get("bid"),
        "ask": market_data.get("ask"),
        "spread_pct": None,
        "bid_qty": None,
        "ask_qty": None,
        "depth_imbalance": market_data.get("depth_imbalance"),
        "quote_age_sec": _quote_age if _quote_age is not None else market_data.get("quote_age_sec"),
        "quote_ts_epoch": market_data.get("quote_ts_epoch"),
        "depth_age_sec": market_data.get("depth_age_sec"),
        "fill_prob_est": getattr(cfg, "EXEC_FILL_PROB", None),
        "portfolio_equity": orch.portfolio.get("capital"),
        "equity": orch.portfolio.get("capital"),
        "equity_high": orch.portfolio.get("equity_high"),
        "daily_pnl": orch.portfolio.get("daily_pnl", orch.portfolio.get("daily_profit", 0.0) + orch.portfolio.get("daily_loss", 0.0)),
        "daily_pnl_pct": orch.portfolio.get("daily_pnl_pct"),
        "drawdown_pct": orch.risk_state.daily_max_drawdown if hasattr(orch.risk_state, "daily_max_drawdown") else None,
        "loss_streak": orch.loss_streak.get(sym, 0),
        "open_risk": orch.portfolio.get("open_risk", orch._open_risk()),
        "open_risk_pct": orch.portfolio.get("open_risk_pct"),
        "delta_exposure": None,
        "gamma_exposure": None,
        "vega_exposure": None,
        "gatekeeper_allowed": 0,
        "veto_reasons": [],
        "risk_allowed": None,
        "exec_guard_allowed": None,
        "pilot_allowed": None,
        "pilot_reasons": [],
        "action_size_multiplier": None,
        "filled_bool": None,
        "fill_price": None,
        "time_to_fill": None,
        "slippage_vs_mid": None,
        "pnl_horizon_5m": None,
        "pnl_horizon_15m": None,
        "mae_15m": None,
        "mfe_15m": None,
    }
