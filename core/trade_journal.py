# core/trade_journal.py

import csv
from datetime import datetime
from pathlib import Path

class TradeJournal:
    def __init__(self, file_path="logs/trade_journal.csv"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(exist_ok=True)
        if not self.file_path.exists():
            with open(self.file_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp","symbol","direction","entry","stoploss",
                    "target","qty","reason","pnl"
                ])

    def log(self, trade, pnl=0):
        with open(self.file_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now(),
                trade["symbol"],
                trade["direction"],
                trade["entry"],
                trade["stoploss"],
                trade["target"],
                trade.get("quantity",1),
                trade.get("reason","ML+Risk"),
                pnl
            ])

