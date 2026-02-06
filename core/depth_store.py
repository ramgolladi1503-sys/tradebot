from collections import defaultdict
import time
import json
from core.trade_store import insert_depth_snapshot

class DepthStore:
    def __init__(self):
        self.books = defaultdict(dict)

    def update(self, instrument_token, depth):
        self.books[instrument_token] = {
            "depth": depth,
            "ts": time.time()
        }
        try:
            # compute imbalance
            buy_qty = sum([b.get("quantity", 0) for b in depth.get("buy", [])])
            sell_qty = sum([s.get("quantity", 0) for s in depth.get("sell", [])])
            imbalance = 0.0
            if buy_qty + sell_qty > 0:
                imbalance = (buy_qty - sell_qty) / (buy_qty + sell_qty)
            insert_depth_snapshot(time.strftime("%Y-%m-%d %H:%M:%S"), instrument_token, json.dumps({"depth": depth, "imbalance": imbalance}))
            # alert on spikes (optional)
            if getattr(__import__("config.config", fromlist=["IMBALANCE_ALERT_ENABLE"]), "IMBALANCE_ALERT_ENABLE", False):
                if abs(imbalance) > getattr(__import__("config.config", fromlist=["IMBALANCE_ALERT"]), "IMBALANCE_ALERT", 0.6):
                    from core.telegram_alerts import send_telegram_message
                    send_telegram_message(f"Depth imbalance spike {imbalance:.2f} for token {instrument_token}")
        except Exception:
            pass

    def get(self, instrument_token):
        return self.books.get(instrument_token)

depth_store = DepthStore()
