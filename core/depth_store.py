from collections import defaultdict, deque
import queue
import threading
import time
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from config import config as cfg
from core.trade_store import insert_depth_snapshot
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer
from core.persistence_durability import record_degradation
from core.kite_depth_protocol import canonicalize_kite_depth
from core.storage_bounds_v37 import MAX_DEPTH_QUEUE_ITEM_BYTES, StorageBoundViolation, depth_queue_item_bytes, require_item_size

_ERROR_LOG_PATH = logs_dir() / "depth_store_errors.jsonl"
_ERROR_LOGGER = get_jsonl_writer(_ERROR_LOG_PATH)
logger = logging.getLogger(__name__)

class DepthStore:
    def __init__(self):
        self.books = defaultdict(dict)
        self._ts_window = deque(maxlen=10000)
        self._last_persist_epoch_by_token = defaultdict(float)
        queue_maxsize = max(
            1,
            int(getattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 16384) or 16384),
        )
        self._persist_queue = queue.Queue(maxsize=queue_maxsize)
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
        self._rejection_path = None
        self._rejection_session_id = ""
        self._rejection_producer_sha = ""
        self._rejection_lock = threading.Lock()

    def configure_rejection_provenance(self, path, *, session_id: str, producer_sha: str) -> None:
        self._rejection_path = Path(path)
        self._rejection_session_id = str(session_id)
        self._rejection_producer_sha = str(producer_sha)

    def _record_rejection(self, *, reason_code: str, instrument_token=None,
                          receipt_epoch: float | None = None, queue_depth=None,
                          stage: str = "depth_persistence") -> None:
        path = self._rejection_path
        if path is None:
            return
        row = {
            "schema_version": 1,
            "session_id": self._rejection_session_id,
            "producer_sha": self._rejection_producer_sha,
            "receipt_epoch": float(receipt_epoch if receipt_epoch is not None else time.time()),
            "instrument_token": instrument_token,
            "reason_code": str(reason_code),
            "stage": str(stage),
            "queue_depth": queue_depth,
        }
        body = json.dumps(row, sort_keys=True, separators=(",", ":"))
        row["row_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._rejection_lock, path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        except Exception as exc:
            logger.error("depth_rejection_provenance_write_failed error=%s", type(exc).__name__)

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
                        self._record_rejection(reason_code="SHUTDOWN_REJECT", instrument_token=instrument_token, receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
                        raise RuntimeError("depth persistence is shut down")
                try:
                    canonical_depth = canonicalize_kite_depth(depth)
                    item_bytes = depth_queue_item_bytes(now_iso, instrument_token, canonical_depth, imbalance)
                except ValueError:
                    # Legacy callers may provide a compact partial book.  The
                    # WebSocket protocol owner remains strict; this store
                    # accepts the legacy shape only when its serialized
                    # envelope still fits the same byte bound.
                    canonical_depth = depth
                    item_bytes = len(json.dumps({"depth": depth, "imbalance": imbalance}, sort_keys=True, separators=(",", ":")).encode("utf-8")) + 110
                require_item_size(item_bytes, MAX_DEPTH_QUEUE_ITEM_BYTES, "DEPTH_QUEUE")
                try:
                    # Apply bounded, time-limited backpressure instead of
                    # dropping a depth snapshot when SQLite briefly falls
                    # behind.  The timeout preserves fail-closed behavior if
                    # the persistence worker is genuinely stalled.
                    put_timeout_sec = max(
                        0.0,
                        float(getattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 1.0) or 1.0),
                    )
                    self._persist_queue.put((
                        now_iso, instrument_token,
                        json.dumps({"depth": canonical_depth, "imbalance": imbalance}, sort_keys=True, separators=(",", ":")), now_epoch,
                    ), timeout=put_timeout_sec)
                except queue.Full:
                    with self._persist_lock:
                        self._persist_rejected += 1
                        self._persist_degraded = True
                        record_degradation("depth", "DEPTH_QUEUE_FULL")
                        self._record_rejection(reason_code="QUEUE_REJECTED", instrument_token=instrument_token, receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
                    logger.error("depth_persistence_queue_full")
                    raise
                with self._persist_lock:
                    self._persist_enqueued += 1
            # alert on spikes (optional)
            if getattr(cfg, "IMBALANCE_ALERT_ENABLE", False):
                if abs(imbalance) > getattr(cfg, "IMBALANCE_ALERT", 0.6):
                    from core.telegram_alerts import send_telegram_message
                    send_telegram_message(f"Depth imbalance spike {imbalance:.2f} for token {instrument_token}")
        except (StorageBoundViolation, ValueError, TypeError) as exc:
            with self._persist_lock:
                self._persist_rejected += 1
                self._persist_degraded = True
            record_degradation("depth", "DEPTH_BOUND_REJECTED")
            self._record_rejection(reason_code="BOUND_REJECTED", instrument_token=instrument_token, receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
            logger.warning("depth_persistence_bound_rejected error=%s", type(exc).__name__)
        except Exception as exc:
            if str(exc) not in {"", "depth persistence is shut down"}:
                self._record_rejection(reason_code="UNKNOWN_REJECTION", instrument_token=instrument_token, receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
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
