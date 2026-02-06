# ==============================
# Kite + Telegram Credentials
# ==============================

import os

# Zerodha Kite (loaded from environment)
API_KEY = os.getenv("KITE_API_KEY", "")
API_SECRET = os.getenv("KITE_API_SECRET", "")

# Telegram Bot (loaded from environment)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
