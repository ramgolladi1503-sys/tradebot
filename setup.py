# setup.py
import os

# Base folders
folders = [
    "trading_bot/config",
    "trading_bot/modules",
    "trading_bot/data"
]

# Module files with boilerplate content
modules = {
    "config/config.py": """# config.py
CAPITAL = 500000
MAX_RISK_PERCENT = 5
LOT_SIZE = {"NIFTY": 60, "BANKNIFTY": 15}
WEEKLY_EXPIRY_DAY = "Tuesday"

TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

KITE_API_KEY = "YOUR_KITE_API_KEY"
KITE_API_SECRET = "YOUR_KITE_API_SECRET"
KITE_ACCESS_TOKEN = "YOUR_FRESH_ACCESS_TOKEN"

SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
""",
    "modules/trade_engine.py": """# trade_engine.py
from config.config import LOT_SIZE, CAPITAL, MAX_RISK_PERCENT
from datetime import date
from market_calendar import next_expiry

def generate_trade_call(symbol, ltp, bias):
    strike = round(ltp / 100) * 100
    option_type = "CE" if bias == "Bullish" else "PE"
    entry_price = max(ltp * 0.004, 50)
    stop_loss = entry_price * 0.8
    target = entry_price * 1.3
    max_risk = CAPITAL * (MAX_RISK_PERCENT / 100)
    lot_size = min(LOT_SIZE.get(symbol, 1), max_risk // (entry_price - stop_loss))
    if date.today() == next_expiry():
        entry_price = max(entry_price * 0.5, 25)
        stop_loss = entry_price * 0.8
        target = entry_price * 2
    return {
        "symbol": symbol,
        "strike": strike,
        "option_type": option_type,
        "entry_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "target": round(target, 2),
        "lot_size": int(lot_size),
        "confidence": 60
    }
""",
    "modules/trade_logger.py": """# trade_logger.py
import json
from datetime import date

LOG_FILE = "data/trade_log.json"

def log_trade(trade):
    try:
        with open(LOG_FILE, "r") as f:
            data = json.load(f)
    except:
        data = []
    trade_entry = {"date": str(date.today()), **trade, "hit_target": False, "hit_stoploss": False}
    data.append(trade_entry)
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def update_trade_status(symbol, strike, option_type, current_price):
    try:
        with open(LOG_FILE, "r") as f:
            data = json.load(f)
    except:
        return False
    updated = False
    for trade in data:
        if trade["symbol"]==symbol and trade["strike"]==strike and trade["option_type"]==option_type:
            if not trade["hit_target"] and current_price >= trade["target"]:
                trade["hit_target"] = True
                updated = True
            elif not trade["hit_stoploss"] and current_price <= trade["stop_loss"]:
                trade["hit_stoploss"] = True
                updated = True
    if updated:
        with open(LOG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    return updated

def daily_summary():
    try:
        with open(LOG_FILE, "r") as f:
            data = json.load(f)
    except:
        return "No trades logged today."
    summary = []
    for trade in data:
        summary.append(f'{trade["symbol"]} {trade["option_type"]} Strike {trade["strike"]} Target: {trade["hit_target"]} Stop: {trade["hit_stoploss"]}')
    return "\\n".join(summary)

def cumulative_summary():
    return daily_summary()

def print_summary(text):
    print(text)
""",
    "modules/premarket.py": """# premarket.py
from config.config import SYMBOLS

def analyze_premarket():
    # Placeholder for pre-market analysis
    bias = "Bullish"  # Replace with live data calculation
    data = {"US_DOW": 38200, "US_NASDAQ": 15400, "US_SP500": 4930, "CRUDE_OIL": 83.5, "USD_INR": 82.2}
    return {"bias": bias, "score": 2, "data": data}
""",
    "modules/intraday_live_tick.py": """# intraday_live_tick.py
from modules.trade_logger import log_trade, update_trade_status
from modules.trade_engine import generate_trade_call
from modules.telegram_alerts import send_telegram

active_trades = []

def live_tick_handler(symbol, current_price, bias):
    existing_trade = next((t for t in active_trades if t["symbol"]==symbol), None)
    if not existing_trade:
        trade = generate_trade_call(symbol, current_price, bias)
        active_trades.append(trade)
        log_trade(trade)
        send_telegram(f"💹 Trade Call:\\n{trade}")
    for trade in active_trades:
        if trade["symbol"]==symbol:
            updated = update_trade_status(symbol, trade["strike"], trade["option_type"], current_price)
            if updated:
                status = "✅ Target Hit" if current_price >= trade["target"] else "❌ Stopped Out"
                send_telegram(f"📈 Trade Update:\\n{symbol} {trade['option_type']} Strike {trade['strike']} - {status}")
""",
    "modules/telegram_alerts.py": """# telegram_alerts.py
import requests
from config.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode":"Markdown"}
    try:
        r = requests.post(url, data=payload)
        return r.status_code==200
    except Exception as e:
        print("Telegram error:", e)
        return False
""",
    "modules/kite_ws.py": """# kite_ws.py
from kiteconnect import KiteTicker
from modules.intraday_live_tick import live_tick_handler
from modules.premarket import analyze_premarket

API_KEY = "YOUR_KITE_API_KEY"
ACCESS_TOKEN = "YOUR_FRESH_ACCESS_TOKEN"

SUBSCRIBE_SYMBOLS = ["NSE:NIFTY 50","NSE:BANKNIFTY","BSE:SENSEX"]

premarket = analyze_premarket()
bias = premarket["bias"]

kws = KiteTicker(API_KEY, ACCESS_TOKEN)

def on_ticks(ws, ticks):
    for tick in ticks:
        sym_str = "NIFTY" if tick['tradingsymbol'].startswith("NIFTY") else \
                   "BANKNIFTY" if tick['tradingsymbol'].startswith("BANKNIFTY") else \
                   "SENSEX" if tick['tradingsymbol'].startswith("SENSEX") else None
        if sym_str:
            live_tick_handler(sym_str, tick["last_price"], bias)

def on_connect(ws, response):
    print("Connected to Kite WebSocket. Subscribing...")
    ws.subscribe(SUBSCRIBE_SYMBOLS)
    ws.set_mode(ws.MODE_FULL, SUBSCRIBE_SYMBOLS)

def on_close(ws, code, reason):
    print(f"WebSocket closed. Code: {code}, Reason: {reason}")

def on_error(ws, code, reason):
    print(f"WebSocket error. Code: {code}, Reason: {reason}")

def start_kite_ws():
    kws.on_ticks = on_ticks
    kws.on_connect = on_connect
    kws.on_close = on_close
    kws.on_error = on_error
    kws.connect(threaded=True)
    print("Kite WebSocket started.")
""",
    "main.py": """# main.py
import time
from datetime import datetime
from modules.premarket import analyze_premarket
from modules.telegram_alerts import send_telegram
from modules.trade_logger import daily_summary, cumulative_summary, print_summary
from modules.kite_ws import start_kite_ws

def run_trading_bot():
    premarket = analyze_premarket()
    bias = premarket["bias"]
    print(f"Pre-Market Bias: {bias}")
    send_telegram(f"📈 Pre-Market Bias: {bias}\\nData: {premarket['data']}")

    print("Starting Kite WebSocket for live trading...")
    start_kite_ws()

    while True:
        now = datetime.now()
        if now.hour==15 and now.minute>=30:
            print("Market closed. Generating reports...")
            daily = daily_summary()
            print_summary(daily)
            send_telegram(f"📊 Daily Summary:\\n{daily}")
            cumulative = cumulative_summary()
            print_summary(cumulative)
            send_telegram(f"📊 Cumulative Summary:\\n{cumulative}")
            break
        else:
            time.sleep(30)

if __name__=="__main__":
    run_trading_bot()
"""
}

# ------------------------
# Create folders
# ------

