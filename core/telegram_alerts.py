import requests
from config import config as cfg

def send_telegram_message(message: str):
    if not cfg.ENABLE_TELEGRAM:
        return
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        return
    if getattr(cfg, "TELEGRAM_ONLY_TRADES", False):
        # allow only trade-related alerts
        allowed_prefixes = ("Trade executed:", "Trade queued:", "Trade approved:", "DayType alert:")
        if not message.startswith(allowed_prefixes):
            return
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cfg.TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Telegram send error: {e}")
