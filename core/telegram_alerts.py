import json
import time
from pathlib import Path
import requests
from config import config as cfg
from core.trade_ticket import TradeTicket


def _log_blocked(reason: str, payload: dict | None = None) -> None:
    try:
        path = Path("logs/telegram_blocked.jsonl")
        path.parent.mkdir(exist_ok=True)
        row = {"ts_epoch": time.time(), "reason": reason}
        if payload:
            row.update(payload)
        with path.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception:
        print("[TELEGRAM_BLOCKED] failed to log")


def send_trade_ticket(ticket: TradeTicket) -> bool:
    if not cfg.ENABLE_TELEGRAM:
        return False
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        _log_blocked("missing_telegram_credentials")
        return False
    actionable, reason = ticket.is_actionable()
    if not actionable:
        _log_blocked("missing_contract_fields", {"detail": reason, "trace_id": ticket.trace_id})
        return False
    message = ticket.format_message()
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cfg.TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
        return True
    except Exception as e:
        _log_blocked("send_error", {"detail": str(e), "trace_id": ticket.trace_id})
        return False


def send_telegram_message(message: str) -> bool:
    if not cfg.ENABLE_TELEGRAM:
        return False
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        _log_blocked("missing_telegram_credentials")
        return False
    if not getattr(cfg, "TELEGRAM_ALLOW_NON_TRADE_ALERTS", False):
        _log_blocked("non_trade_blocked", {"message": message[:200]})
        return False
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cfg.TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
        return True
    except Exception as e:
        _log_blocked("send_error", {"detail": str(e)})
        return False
