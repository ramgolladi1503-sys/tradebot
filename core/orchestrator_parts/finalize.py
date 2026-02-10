from config import config as cfg
from core.audit_log import append_event as audit_append
from core.incidents import create_incident
from core.telegram_alerts import send_telegram_message
from core.time_utils import now_ist, now_utc_epoch
from ml.strategy_decay_predictor import generate_decay_report, telegram_summary


def validate_market_snapshot(orch, market_data: dict):
    if bool(market_data.get("valid", True)):
        return True, False
    symbol = market_data.get("symbol")
    reason = str(market_data.get("invalid_reason") or "invalid_snapshot")
    reason_codes = list(market_data.get("invalid_reason_codes") or [])
    feed_health = market_data.get("feed_health") or {}
    try:
        veto = [reason]
        for code in reason_codes:
            if code and code not in veto:
                veto.append(str(code))
        event = orch._build_decision_event(None, market_data, gatekeeper_allowed=False, veto_reasons=veto)
        orch._log_decision_safe(event)
    except Exception:
        pass
    try:
        audit_append(
            {
                "event": "INVALID_SNAPSHOT",
                "symbol": symbol,
                "reason": reason,
                "reason_codes": reason_codes,
                "feed_health": feed_health,
                "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
            }
        )
    except Exception:
        pass
    try:
        create_incident(
            "SEV2",
            "INVALID_SNAPSHOT",
            {
                "symbol": symbol,
                "reason": reason,
                "reason_codes": reason_codes,
                "ltp": market_data.get("ltp"),
                "ltp_source": market_data.get("ltp_source"),
                "feed_health": feed_health,
            },
        )
    except Exception:
        pass
    action = str(getattr(cfg, "INVALID_LTP_ACTION", "skip_symbol")).lower()
    return False, action == "halt_cycle"


def pilot_trade_gate(orch, trade, market_data):
    if not getattr(cfg, "LIVE_PILOT_MODE", False):
        return True, []
    reasons = []
    whitelist = getattr(cfg, "LIVE_STRATEGY_WHITELIST", [])
    if whitelist and trade.strategy not in whitelist:
        reasons.append("pilot_strategy_not_whitelisted")
    opt = orch._match_option_snapshot(trade, market_data)
    quote_ts = (opt or {}).get("quote_ts") or market_data.get("quote_ts")
    quote_age = orch._quote_age_sec(quote_ts)
    max_age = float(getattr(cfg, "LIVE_MAX_QUOTE_AGE_SEC", getattr(cfg, "MAX_QUOTE_AGE_SEC", 2.0)))
    if quote_age is None or quote_age > max_age:
        reasons.append("pilot_quote_stale")
    bid = (opt or {}).get("bid") or trade.opt_bid
    ask = (opt or {}).get("ask") or trade.opt_ask
    spread_pct = None
    if bid and ask:
        base = (opt or {}).get("ltp") or trade.opt_ltp or ((bid + ask) / 2.0)
        if base:
            spread_pct = (ask - bid) / base
    max_spread = float(getattr(cfg, "LIVE_MAX_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.03)))
    if spread_pct is None or spread_pct > max_spread:
        reasons.append("pilot_spread_too_wide")
    if reasons:
        return False, reasons
    return True, []


def refresh_decay_report(orch):
    try:
        today = now_ist().date()
        if orch._last_decay_date == today:
            return
        report = generate_decay_report()
        probs = report.get("decay_probabilities", {})
        orch.strategy_tracker.apply_decay_probs(probs)
        if getattr(cfg, "TELEGRAM_ENABLE", False):
            try:
                send_telegram_message(telegram_summary(report))
            except Exception:
                pass
        orch._last_decay_date = today
    except Exception:
        pass
