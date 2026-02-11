from collections import defaultdict, deque
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from core.trade_store import insert_depth_snapshot
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer

_ERROR_LOG_PATH = logs_dir() / "depth_store_errors.jsonl"
_ERROR_LOGGER = get_jsonl_writer(_ERROR_LOG_PATH)

class DepthStore:
    def __init__(self):
        self.books = defaultdict(dict)
        self._ts_window = deque(maxlen=10000)

    def update(self, instrument_token, depth):
        now_epoch = time.time()
        now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        self._ts_window.append(now_epoch)
        self.books[instrument_token] = {
            "depth": depth,
            "ts": now_epoch,
            "ts_epoch": now_epoch,
            "ts_iso": now_iso,
        }
        try:
            # compute imbalance
            buy_qty = sum([b.get("quantity", 0) for b in depth.get("buy", [])])
            sell_qty = sum([s.get("quantity", 0) for s in depth.get("sell", [])])
            imbalance = 0.0
            if buy_qty + sell_qty > 0:
                imbalance = (buy_qty - sell_qty) / (buy_qty + sell_qty)
            insert_depth_snapshot(now_iso, instrument_token, json.dumps({"depth": depth, "imbalance": imbalance}), now_epoch)
            # alert on spikes (optional)
            if getattr(__import__("config.config", fromlist=["IMBALANCE_ALERT_ENABLE"]), "IMBALANCE_ALERT_ENABLE", False):
                if abs(imbalance) > getattr(__import__("config.config", fromlist=["IMBALANCE_ALERT"]), "IMBALANCE_ALERT", 0.6):
                    from core.telegram_alerts import send_telegram_message
                    send_telegram_message(f"Depth imbalance spike {imbalance:.2f} for token {instrument_token}")
        except Exception as exc:
            try:
                ok = _ERROR_LOGGER.write({
                    "ts_epoch": now_epoch,
                    "event": "DEPTH_STORE_ERROR",
                    "instrument_token": instrument_token,
                    "error": str(exc),
                })
                if not ok:
                    print(f"[DEPTH_STORE_ERROR] failed to log path={_ERROR_LOG_PATH} err=write_failed")
            except Exception as log_exc:
                print(f"[DEPTH_STORE_ERROR] failed to log path={_ERROR_LOG_PATH} err={type(log_exc).__name__}:{log_exc}")

    def get(self, instrument_token):
        return self.books.get(instrument_token)

    def msgs_last_min(self) -> int:
        now = time.time()
        while self._ts_window and now - self._ts_window[0] > 60:
            self._ts_window.popleft()
        return len(self._ts_window)

depth_store = DepthStore()
