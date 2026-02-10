import json
import time
from pathlib import Path

from config import config as cfg
from core.time_utils import now_ist, now_utc_epoch
from core.trade_schema import build_instrument_id, validate_trade_identity
from core.trade_ticket import TradeTicket


def build_decision_event(orch, trade, market_data: dict, gatekeeper_allowed: bool, veto_reasons=None, pilot_allowed=None, pilot_reasons=None):
    now_text = now_ist().isoformat()
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
    if trade:
        instrument_type = getattr(trade, "instrument_type", None) or getattr(trade, "instrument", None)
        right = getattr(trade, "right", None) or getattr(trade, "option_type", None)
        expiry = getattr(trade, "expiry", None)
        strike = getattr(trade, "strike", None)
    instrument_id = None
    if trade and instrument_type:
        instrument_id = build_instrument_id(trade.symbol, instrument_type, expiry, strike, right)
    event = {
        "trade_id": trade.trade_id if trade else None,
        "ts": now_text,
        "symbol": (trade.symbol if trade else market_data.get("symbol")),
        "strategy_id": trade.strategy if trade else None,
        "regime": market_data.get("regime") or (trade.regime if trade else None),
        "regime_probs": market_data.get("regime_probs"),
        "shock_score": market_data.get("shock_score"),
        "side": trade.side if trade else None,
        "instrument": trade.instrument if trade else None,
        "instrument_id": instrument_id,
        "strike": strike,
        "expiry": expiry,
        "option_type": getattr(trade, "option_type", None) if trade else None,
        "right": right,
        "instrument_type": instrument_type,
        "underlying": trade.symbol if trade else None,
        "qty_lots": getattr(trade, "qty_lots", None) if trade else None,
        "qty_units": getattr(trade, "qty_units", None) if trade else None,
        "validity_sec": getattr(trade, "validity_sec", None) if trade else None,
        "dte": orch._calc_dte(getattr(trade, "expiry", None)) if trade else None,
        "expiry_bucket": market_data.get("expiry_type") or market_data.get("expiry_bucket"),
        "score_0_100": getattr(trade, "trade_score", None) if trade else None,
        "xgb_proba": trade.confidence if trade and getattr(trade, "model_type", None) == "xgb" else None,
        "deep_proba": trade.confidence if trade and getattr(trade, "model_type", None) == "deep" else None,
        "micro_proba": (opt or {}).get("micro_pred"),
        "ensemble_proba": getattr(trade, "alpha_confidence", None) if trade else None,
        "ensemble_uncertainty": getattr(trade, "alpha_uncertainty", None) if trade else None,
        "champion_proba": getattr(trade, "confidence", None) if trade else None,
        "challenger_proba": getattr(trade, "shadow_confidence", None) if trade else None,
        "champion_model_id": getattr(trade, "model_version", None) if trade else None,
        "challenger_model_id": getattr(trade, "shadow_model_version", None) if trade else None,
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
        "feed_health": market_data.get("feed_health"),
        "time_sanity": market_data.get("time_sanity"),
        "fill_prob_est": getattr(cfg, "EXEC_FILL_PROB", None),
        "portfolio_equity": orch.portfolio.get("capital"),
        "equity": orch.portfolio.get("capital"),
        "equity_high": orch.portfolio.get("equity_high"),
        "daily_pnl": orch.portfolio.get("daily_pnl", orch.portfolio.get("daily_profit", 0.0) + orch.portfolio.get("daily_loss", 0.0)),
        "daily_pnl_pct": orch.portfolio.get("daily_pnl_pct"),
        "drawdown_pct": orch.risk_state.daily_max_drawdown if hasattr(orch.risk_state, "daily_max_drawdown") else None,
        "loss_streak": orch.loss_streak.get(trade.symbol, 0) if trade else 0,
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
    if event.get("instrument_id") is None and trade:
        ok, _reason = validate_trade_identity(
            trade.symbol,
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
        event["quote_age_sec"] = -1.0
        if "epoch_missing" not in veto_reasons:
            veto_reasons.append("epoch_missing")
        event["veto_reasons"] = veto_reasons
    return event


def log_identity_error(_orch, trade, extra: dict | None = None) -> None:
    try:
        path = Path("logs/trade_identity_errors.jsonl")
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
        with path.open("a") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


def log_decision_safe(orch, event: dict, trade=None, log_decision_fn=None):
    if event.get("instrument_id") is None:
        log_identity_error(orch, trade or event, {"reason": "missing_contract_fields"})
        return None
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
        return build_instrument_id(trade.symbol, instrument_type, expiry, strike, right)
    except Exception:
        return None


def build_trade_ticket(orch, trade, _market_data: dict) -> TradeTicket:
    validity = int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180))
    reason_codes = []
    if getattr(trade, "regime", None):
        reason_codes.append(f"regime:{trade.regime}")
    if getattr(trade, "strategy", None):
        reason_codes.append(f"strategy:{trade.strategy}")
    for blocked_reason in list(getattr(trade, "tradable_reasons_blocking", []) or []):
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
    meta = orch.trade_meta.get(getattr(trade, "trade_id", ""), {}) or {}
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
        stats = dict(orch.strategy_tracker.stats.get(trade.strategy, {}) or {})
        decay = orch.strategy_tracker.decay_probs.get(trade.strategy, {})
        if decay:
            stats.update(decay)
        try:
            baseline_weight = float(orch.strategy_allocator._weight(trade.strategy))
        except Exception:
            baseline_weight = 1.0
        suggestion = orch.meta_model.suggest(
            trade.strategy,
            getattr(trade, "model_type", None),
            market_data,
            stats,
        )
        payload = {
            "ts_epoch": now_utc_epoch(),
            "symbol": trade.symbol,
            "strategy": trade.strategy,
            "trade_id": trade.trade_id,
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
        "quote_age_sec": orch._quote_age_sec(market_data.get("quote_ts")) or market_data.get("quote_age_sec"),
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
