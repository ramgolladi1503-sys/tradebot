from collections import defaultdict, deque
import queue
import threading
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from config import config as cfg
from core.trade_store import insert_depth_snapshot
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer
from core.persistence_durability import record_degradation

_ERROR_LOG_PATH = logs_dir() / "depth_store_errors.jsonl"
_ERROR_LOGGER = get_jsonl_writer(_ERROR_LOG_PATH)
logger = logging.getLogger(__name__)

class DepthStore:
    def __init__(self):
        self.books = defaultdict(dict)
        self._ts_window = deque(maxlen=10000)
        self._last_persist_epoch_by_token = defaultdict(float)
        self._persist_queue = queue.Queue(maxsize=2048)
        self._persist_stop = threading.Event()
        self._persist_lock = threading.Lock()
        self._persist_enqueued = 0
        self._persisted = 0
        self._persist_rejected = 0
        self._persist_failures = 0
        self._persist_degraded = False
        self._persist_shutdown = False
        self._persist_thread = threading.Thread(target=self._persist_loop, name="depth-store-persistence", daemon=True)
        self._persist_thread.start()

    def _persist_loop(self):
        while not self._persist_stop.is_set() or not self._persist_queue.empty():
            try:
                item = self._persist_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                insert_depth_snapshot(*item)
                with self._persist_lock:
                    self._persisted += 1
            except Exception as exc:
                with self._persist_lock:
                    self._persist_failures += 1
                    self._persist_degraded = True
                    record_degradation("depth", "DEPTH_PERSISTENCE_FAILURE")
                logger.warning("depth_persistence_failed error=%s", type(exc).__name__)
            finally:
                self._persist_queue.task_done()

    def _should_persist_snapshot(self, instrument_token, now_epoch: float) -> bool:
        min_interval_sec = max(
            0.0,
            float(getattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.5) or 0.5),
        )
        if min_interval_sec <= 0.0:
            self._last_persist_epoch_by_token[instrument_token] = now_epoch
            return True
        last_epoch = float(self._last_persist_epoch_by_token.get(instrument_token) or 0.0)
        if (now_epoch - last_epoch) >= min_interval_sec:
            self._last_persist_epoch_by_token[instrument_token] = now_epoch
            return True
        return False

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
            if self._should_persist_snapshot(instrument_token, now_epoch):
                with self._persist_lock:
                    if self._persist_shutdown:
                        self._persist_rejected += 1
                        self._persist_degraded = True
                        record_degradation("depth", "DEPTH_PERSISTENCE_SHUTDOWN")
                        raise RuntimeError("depth persistence is shut down")
                try:
                    self._persist_queue.put_nowait((
                        now_iso, instrument_token,
                        json.dumps({"depth": depth, "imbalance": imbalance}), now_epoch,
                    ))
                except queue.Full:
                    with self._persist_lock:
                        self._persist_rejected += 1
                        self._persist_degraded = True
                        record_degradation("depth", "DEPTH_QUEUE_FULL")
                    logger.error("depth_persistence_queue_full")
                    raise
                with self._persist_lock:
                    self._persist_enqueued += 1
            # alert on spikes (optional)
            if getattr(cfg, "IMBALANCE_ALERT_ENABLE", False):
                if abs(imbalance) > getattr(cfg, "IMBALANCE_ALERT", 0.6):
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
                    logger.error("depth_store_error_log_write_failed path=%s", _ERROR_LOG_PATH)
            except Exception as log_exc:
                logger.error("depth_store_error_log_failed path=%s err=%s:%s", _ERROR_LOG_PATH, type(log_exc).__name__, log_exc)

    def persistence_state(self) -> dict:
        with self._persist_lock:
            return {
                "queue_depth": self._persist_queue.qsize(),
                "enqueued": self._persist_enqueued,
                "persisted": self._persisted,
                "rejected": self._persist_rejected,
                "failures": self._persist_failures,
                "durability_degraded": self._persist_degraded,
                "shutdown": self._persist_shutdown,
                "worker_alive": self._persist_thread.is_alive(),
            }

    def shutdown_persistence(self, deadline_seconds: float = 2.0) -> dict:
        with self._persist_lock:
            self._persist_shutdown = True
        deadline = time.monotonic() + max(0.0, float(deadline_seconds))
        while self._persist_queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        self._persist_stop.set()
        self._persist_thread.join(max(0.0, deadline - time.monotonic()))
        state = self.persistence_state()
        state["complete"] = state["queue_depth"] == 0 and not state["worker_alive"]
        return state

    def get(self, instrument_token):
        return self.books.get(instrument_token)

    def msgs_last_min(self) -> int:
        now = time.time()
        while self._ts_window and now - self._ts_window[0] > 60:
            self._ts_window.popleft()
        return len(self._ts_window)

depth_store = DepthStore()
