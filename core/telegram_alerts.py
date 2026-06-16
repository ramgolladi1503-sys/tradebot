import json
import logging
import time
from pathlib import Path
import requests
from config import config as cfg
from core.trade_ticket import TradeTicket
from core.paths import logs_dir


logger = logging.getLogger(__name__)


def _log_blocked(reason: str, payload: dict | None = None) -> None:
    try:
        path = logs_dir() / "telegram_blocked.jsonl"
        path.parent.mkdir(exist_ok=True)
        row = {"ts_epoch": time.time(), "reason": reason}
        if payload:
            row.update(payload)
        with path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        logger.error("telegram_blocked_log_failed")


def send_trade_ticket(ticket: TradeTicket) -> bool:
    if not cfg.ENABLE_TELEGRAM:
        return False
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        _log_blocked("missing_telegram_credentials")
        return False
    if getattr(ticket, "tradable", True) is False:
        message = ticket.format_market_note()
        _log_blocked(
            "non_tradable_market_note",
            {
                "trace_id": ticket.trace_id,
                "reasons": list(getattr(ticket, "tradable_reasons_blocking", []) or []),
            },
        )
    else:
        actionable, reason = ticket.is_actionable()
        if not actionable:
            _log_blocked("missing_contract", {"detail": reason, "trace_id": ticket.trace_id})
            return False
        message = ticket.format_message()
    if not getattr(cfg, "TELEGRAM_BOT_TOKEN", None) or not getattr(cfg, "TELEGRAM_CHAT_ID", None):
        _log_blocked("missing_telegram_credentials")
        return False
        
    import threading

    def _fire_and_forget(url: str, payload: dict):
        try:
            requests.post(url, data=payload, timeout=5.0)
        except Exception as e:
            _log_blocked("send_error_async", {"detail": str(e), "trace_id": ticket.trace_id})

    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cfg.TELEGRAM_CHAT_ID, "text": message}
    threading.Thread(target=_fire_and_forget, args=(url, payload), daemon=True).start()
    return True


def send_telegram_message(message: str) -> bool:
    if not cfg.ENABLE_TELEGRAM:
        return False
    if not getattr(cfg, "TELEGRAM_BOT_TOKEN", None) or not getattr(cfg, "TELEGRAM_CHAT_ID", None):
        _log_blocked("missing_telegram_credentials")
        return False
    if not getattr(cfg, "TELEGRAM_ALLOW_NON_TRADE_ALERTS", False):
        _log_blocked("non_trade_blocked", {"message": message[:200]})
        return False

    import threading

    def _fire_and_forget(url: str, payload: dict):
        try:
            requests.post(url, data=payload, timeout=5.0)
        except Exception as e:
            _log_blocked("send_error_async", {"detail": str(e)})

    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cfg.TELEGRAM_CHAT_ID, "text": message}
    threading.Thread(target=_fire_and_forget, args=(url, payload), daemon=True).start()
    return True
