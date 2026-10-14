from collections import defaultdict, deque
import queue
import threading
import time
import json
import logging
import hashlib
import math
from pathlib import Path
from datetime import datetime, timezone
from config import config as cfg
from config import feed_runtime_reliability as reliability_cfg
from core.trade_store import insert_depth_snapshot, insert_depth_snapshots_batch
_DEFAULT_INSERT_DEPTH_SNAPSHOT = insert_depth_snapshot
from core.paths import logs_dir
from core.log_writer import get_jsonl_writer
from core.persistence_durability import record_degradation
from core.kite_depth_protocol import canonicalize_kite_depth
from core.storage_bounds_v37 import (
    DEPTH_QUEUE_MAX_ITEMS,
    MAX_DEPTH_QUEUE_ITEM_BYTES,
    PERSISTENCE_BATCH_MAX_ITEMS,
    StorageBoundViolation,
    depth_queue_item_bytes,
    require_item_size,
)

_ERROR_LOG_PATH = logs_dir() / "depth_store_errors.jsonl"
_ERROR_LOGGER = get_jsonl_writer(_ERROR_LOG_PATH)
logger = logging.getLogger(__name__)

from dataclasses import dataclass
from typing import Literal, Mapping, Any

DepthState = Literal["VALID_BOOK", "EMPTY_BOOK", "ONE_SIDED_BOOK", "CROSSED_BOOK", "INVALID_BOOK"]

@dataclass(frozen=True, slots=True)
class DepthImbalanceResult:
    imbalance: float
    buy_qty: int
    sell_qty: int
    depth_state: DepthState
    is_valid: bool
    spread: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "imbalance": self.imbalance,
            "buy_qty": self.buy_qty,
            "sell_qty": self.sell_qty,
            "depth_state": self.depth_state,
            "is_valid": self.is_valid,
            "spread": self.spread,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
        }

def compute_depth_imbalance(depth: Mapping[str, Any] | None) -> DepthImbalanceResult:
    """Pure, deterministic computation of L2 orderbook depth imbalance with microstructure validation.

    Guarantees:
    - Never raises an unhandled exception.
    - math.isfinite(result.imbalance) is True.
    - -1.0 <= result.imbalance <= 1.0.
    - Non-negative integer quantities.
    - Exact state classification (VALID_BOOK, EMPTY_BOOK, ONE_SIDED_BOOK, CROSSED_BOOK, INVALID_BOOK).
    """
    if not isinstance(depth, Mapping):
        return DepthImbalanceResult(
            imbalance=0.0,
            buy_qty=0,
            sell_qty=0,
            depth_state="INVALID_BOOK",
            is_valid=False,
        )

    raw_buys = depth.get("buy") or []
    raw_sells = depth.get("sell") or []
    if not isinstance(raw_buys, list) or not isinstance(raw_sells, list):
        return DepthImbalanceResult(
            imbalance=0.0,
            buy_qty=0,
            sell_qty=0,
            depth_state="INVALID_BOOK",
            is_valid=False,
        )

    # Validate and extract buy levels
    parsed_buys = []
    prev_bid_px = None
    for b in raw_buys:
        if not isinstance(b, Mapping):
            continue
        try:
            px = float(b.get("price", 0.0) or 0.0)
            qty = int(b.get("quantity", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            return DepthImbalanceResult(
                imbalance=0.0,
                buy_qty=0,
                sell_qty=0,
                depth_state="INVALID_BOOK",
                is_valid=False,
            )
        if not math.isfinite(px) or px < 0.0 or qty < 0:
            return DepthImbalanceResult(
                imbalance=0.0,
                buy_qty=0,
                sell_qty=0,
                depth_state="INVALID_BOOK",
                is_valid=False,
            )
        if qty > 0:
            if px > 0.0 and prev_bid_px is not None and px >= prev_bid_px:
                # Monotonicity violation: bid prices must descend strictly
                return DepthImbalanceResult(
                    imbalance=0.0,
                    buy_qty=0,
                    sell_qty=0,
                    depth_state="INVALID_BOOK",
                    is_valid=False,
                )
            if px > 0.0:
                prev_bid_px = px
            parsed_buys.append((px if px > 0.0 else None, qty))

    # Validate and extract sell levels
    parsed_sells = []
    prev_ask_px = None
    for s in raw_sells:
        if not isinstance(s, Mapping):
            continue
        try:
            px = float(s.get("price", 0.0) or 0.0)
            qty = int(s.get("quantity", 0) or 0)
        except (TypeError, ValueError, OverflowError):
            return DepthImbalanceResult(
                imbalance=0.0,
                buy_qty=0,
                sell_qty=0,
                depth_state="INVALID_BOOK",
                is_valid=False,
            )
        if not math.isfinite(px) or px < 0.0 or qty < 0:
            return DepthImbalanceResult(
                imbalance=0.0,
                buy_qty=0,
                sell_qty=0,
                depth_state="INVALID_BOOK",
                is_valid=False,
            )
        if qty > 0:
            if px > 0.0 and prev_ask_px is not None and px <= prev_ask_px:
                # Monotonicity violation: ask prices must ascend strictly
                return DepthImbalanceResult(
                    imbalance=0.0,
                    buy_qty=0,
                    sell_qty=0,
                    depth_state="INVALID_BOOK",
                    is_valid=False,
                )
            if px > 0.0:
                prev_ask_px = px
            parsed_sells.append((px if px > 0.0 else None, qty))

    buy_qty = sum(q for _, q in parsed_buys)
    sell_qty = sum(q for _, q in parsed_sells)
    best_bid = parsed_buys[0][0] if parsed_buys else None
    best_ask = parsed_sells[0][0] if parsed_sells else None

    # Empty book check
    if buy_qty == 0 and sell_qty == 0:
        return DepthImbalanceResult(
            imbalance=0.0,
            buy_qty=0,
            sell_qty=0,
            depth_state="EMPTY_BOOK",
            is_valid=False,
            spread=None,
            best_bid=None,
            best_ask=None,
        )

    # Crossed book check when both sides exist
    if best_bid is not None and best_ask is not None:
        if best_bid >= best_ask:
            return DepthImbalanceResult(
                imbalance=0.0,
                buy_qty=buy_qty,
                sell_qty=sell_qty,
                depth_state="CROSSED_BOOK",
                is_valid=False,
                spread=round(best_ask - best_bid, 4),
                best_bid=best_bid,
                best_ask=best_ask,
            )

    # One-sided liquidity
    if buy_qty > 0 and sell_qty == 0:
        return DepthImbalanceResult(
            imbalance=1.0,
            buy_qty=buy_qty,
            sell_qty=0,
            depth_state="ONE_SIDED_BOOK",
            is_valid=True,
            spread=None,
            best_bid=best_bid,
            best_ask=None,
        )
    if sell_qty > 0 and buy_qty == 0:
        return DepthImbalanceResult(
            imbalance=-1.0,
            buy_qty=0,
            sell_qty=sell_qty,
            depth_state="ONE_SIDED_BOOK",
            is_valid=True,
            spread=None,
            best_bid=None,
            best_ask=best_ask,
        )

    # Valid uncrossed two-sided book
    total_qty = buy_qty + sell_qty
    raw_imb = (buy_qty - sell_qty) / total_qty
    clamped_imb = max(-1.0, min(1.0, float(raw_imb)))
    spread = round(best_ask - best_bid, 4) if (best_bid is not None and best_ask is not None) else None

    return DepthImbalanceResult(
        imbalance=clamped_imb,
        buy_qty=buy_qty,
        sell_qty=sell_qty,
        depth_state="VALID_BOOK",
        is_valid=True,
        spread=spread,
        best_bid=best_bid,
        best_ask=best_ask,
    )

def _retention_prune_allowed(*, queue_depth: int, in_flight: int) -> bool:
    """Retention maintenance must yield to any pending persistence work."""
    return int(queue_depth) == 0 and int(in_flight) == 0

class DepthStore:
    def __init__(self):
        self.books = defaultdict(dict)
        self._ts_window = deque(maxlen=10000)
        self._last_persist_epoch_by_token = defaultdict(float)
        raw_queue_maxsize = getattr(cfg, "DEPTH_PERSIST_QUEUE_MAXSIZE", 32768)
        try:
            queue_maxsize = int(raw_queue_maxsize)
        except (TypeError, ValueError) as exc:
            logger.error("depth_persist_queue_maxsize_invalid value=%r", raw_queue_maxsize)
            raise ValueError("DEPTH_PERSIST_QUEUE_MAXSIZE_INVALID") from exc
        if not 1 <= queue_maxsize <= DEPTH_QUEUE_MAX_ITEMS:
            logger.error(
                "depth_persist_queue_maxsize_out_of_bounds configured=%s allowed_min=1 allowed_max=%s",
                queue_maxsize,
                DEPTH_QUEUE_MAX_ITEMS,
            )
            raise ValueError("DEPTH_PERSIST_QUEUE_MAXSIZE_OUT_OF_BOUNDS")
        raw_batch_size = getattr(cfg, "DEPTH_PERSIST_BATCH_SIZE", None)
        try:
            numeric_batch_size = float(raw_batch_size)
        except (OverflowError, TypeError, ValueError) as exc:
            logger.error("depth_persist_batch_size_invalid value=%r", raw_batch_size)
            raise ValueError("DEPTH_PERSIST_BATCH_SIZE_INVALID") from exc
        if (
            isinstance(raw_batch_size, bool)
            or not math.isfinite(numeric_batch_size)
            or not numeric_batch_size.is_integer()
        ):
            logger.error("depth_persist_batch_size_invalid value=%r", raw_batch_size)
            raise ValueError("DEPTH_PERSIST_BATCH_SIZE_INVALID")
        batch_size = int(numeric_batch_size)
        if not 1 <= batch_size <= PERSISTENCE_BATCH_MAX_ITEMS:
            logger.error(
                "depth_persist_batch_size_out_of_bounds configured=%s allowed_min=1 allowed_max=%s",
                batch_size,
                PERSISTENCE_BATCH_MAX_ITEMS,
            )
            raise ValueError("DEPTH_PERSIST_BATCH_SIZE_OUT_OF_BOUNDS")
        self._persist_queue = queue.Queue(maxsize=queue_maxsize)
        self._persist_batch_size = batch_size
        self._persist_admission_lock = threading.Lock()
        self._persist_wakeup = threading.Event()
        self._persist_stop = threading.Event()
        self._persist_lock = threading.Lock()
        self._persist_enqueued = 0
        self._raw_updates_seen = 0
        self._sample_windows = 0
        self._coalesced_updates = 0
        self._depth_duplicates = 0
        self._persist_in_flight = 0
        self._persisted = 0
        self._persist_queue_rejected = 0
        self._persist_pre_enqueue_rejected = 0
        self._persist_provenance_write_failures = 0
        self._persist_failures = 0
        self._persist_degraded = False
        self._sampling_interval_config_invalid = False
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
            with self._persist_lock:
                self._persist_provenance_write_failures += 1
            logger.error("depth_rejection_provenance_write_failed error=%s", type(exc).__name__)

    def _persist_loop(self):
        min_batch_size = self._persist_batch_size
        adaptive_enabled = bool(getattr(cfg, "PERSISTENCE_BATCH_ADAPTIVE_ENABLED", False))
        configured_max = getattr(cfg, "PERSISTENCE_BATCH_MAX_ITEMS", None)
        if adaptive_enabled or configured_max is not None:
            max_batch_size = max(min_batch_size, int(configured_max or min_batch_size))
        else:
            max_batch_size = min_batch_size
        prune_interval_sec = max(
            5.0,
            float(getattr(cfg, "DEPTH_SNAPSHOT_PRUNE_INTERVAL_SEC", 30.0) or 30.0),
        )
        wal_interval_sec = max(
            5.0,
            float(getattr(cfg, "WAL_CHECKPOINT_MIN_INTERVAL_SEC", 30.0) or 30.0),
        )
        last_prune_mono = time.monotonic()
        last_wal_mono = time.monotonic()
        from core.trade_store import prune_depth_snapshots, checkpoint_depth_wal

        while not self._persist_stop.is_set() or not self._persist_queue.empty():
            items = []
            with self._persist_admission_lock:
                current_q = self._persist_queue.qsize()
                effective_batch_size = min(max_batch_size, max(min_batch_size, current_q)) if max_batch_size > min_batch_size else min_batch_size
                while len(items) < effective_batch_size:
                    try:
                        items.append(self._persist_queue.get_nowait())
                        with self._persist_lock:
                            self._persist_in_flight += 1
                    except queue.Empty:
                        break
                if not items:
                    # Clear while serialized with producers: a later admission
                    # sets the event after publishing its queue item.
                    self._persist_wakeup.clear()

            if not items:
                self._persist_wakeup.wait(timeout=0.1)
                continue

            if items:
                try:
                    rejection_rows = []
                    if insert_depth_snapshot is not _DEFAULT_INSERT_DEPTH_SNAPSHOT:
                        persisted_count = 0
                        for item in items:
                            if insert_depth_snapshot(*item):
                                persisted_count += 1
                    elif len(items) == 1:
                        ok = insert_depth_snapshot(*items[0])
                        persisted_count = 1 if ok else 0
                    else:
                        persisted_count = insert_depth_snapshots_batch(items)

                    skipped_count = len(items) - persisted_count
                    with self._persist_lock:
                        self._persist_in_flight -= len(items)
                        self._persisted += persisted_count
                        if skipped_count > 0:
                            self._persist_queue_rejected += skipped_count
                            self._persist_degraded = True
                            record_degradation("depth", "DEPTH_LOCK_SKIPPED")
                            for item in items[persisted_count:]:
                                token = item[1] if len(item) > 1 else None
                                receipt_epoch = item[3] if len(item) > 3 else time.time()
                                rejection_rows.append(("LOCK_SKIPPED", token, receipt_epoch))
                    for reason_code, token, receipt_epoch in rejection_rows:
                        self._record_rejection(reason_code=reason_code, instrument_token=token,
                                               receipt_epoch=receipt_epoch, queue_depth=self._persist_queue.qsize())
                except Exception as exc:
                    with self._persist_lock:
                        self._persist_in_flight -= len(items)
                        self._persist_failures += len(items)
                        self._persist_degraded = True
                        record_degradation("depth", "DEPTH_PERSISTENCE_FAILURE")
                    for item in items:
                        token = item[1] if len(item) > 1 else None
                        receipt_epoch = item[3] if len(item) > 3 else time.time()
                        self._record_rejection(reason_code="PERSISTENCE_FAILURE", instrument_token=token,
                                               receipt_epoch=receipt_epoch, queue_depth=self._persist_queue.qsize())
                    logger.warning("depth_persistence_failed count=%d error=%s", len(items), type(exc).__name__)
                finally:
                    for _ in items:
                        self._persist_queue.task_done()

            # Run retention pruning & non-blocking WAL checkpoints only when queue occupancy is low/idle.
            now_mono = time.monotonic()
            queue_idle = _retention_prune_allowed(
                queue_depth=self._persist_queue.qsize(),
                in_flight=self._persist_in_flight,
            )
            if (now_mono - last_prune_mono) >= prune_interval_sec and queue_idle:
                last_prune_mono = now_mono
                try:
                    prune_depth_snapshots()
                except Exception as prune_exc:
                    logger.debug("background_depth_prune_skipped err=%s", prune_exc)

            if (now_mono - last_wal_mono) >= wal_interval_sec and self._persist_queue.qsize() < min_batch_size:
                last_wal_mono = now_mono
                try:
                    checkpoint_depth_wal(mode="PASSIVE")
                except Exception as wal_exc:
                    logger.debug("background_wal_checkpoint_skipped err=%s", wal_exc)

    def _should_persist_snapshot(self, instrument_token, now_epoch: float) -> bool:
        min_interval_sec = self._sampling_interval_sec()
        if min_interval_sec <= 0.0:
            self._last_persist_epoch_by_token[instrument_token] = now_epoch
            return True
        last_epoch = float(self._last_persist_epoch_by_token.get(instrument_token) or 0.0)
        if (now_epoch - last_epoch) >= min_interval_sec:
            self._last_persist_epoch_by_token[instrument_token] = now_epoch
            return True
        return False

    def _sampling_interval_sec(self) -> float:
        raw = getattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.5)
        try:
            interval = float(0.5 if raw is None else raw)
        except (TypeError, ValueError, OverflowError):
            interval = math.nan
        if math.isfinite(interval) and interval >= 0.0:
            return interval
        with self._persist_lock:
            first_invalid = not self._sampling_interval_config_invalid
            self._sampling_interval_config_invalid = True
            self._persist_degraded = True
        if first_invalid:
            record_degradation("depth", "DEPTH_SAMPLING_INTERVAL_INVALID")
            logger.warning("depth_sampling_interval_invalid; using conservative 0.5s default")
        return 0.5

    def update(self, instrument_token, depth):
        now_epoch = time.time()
        with self._persist_lock:
            self._raw_updates_seen += 1
        now_iso = datetime.fromtimestamp(now_epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        self._ts_window.append(now_epoch)
        res = compute_depth_imbalance(depth)
        imbalance = res.imbalance
        if res.depth_state == "CROSSED_BOOK":
            record_degradation("depth", "DEPTH_CROSSED_BOOK")
        elif res.depth_state == "INVALID_BOOK":
            record_degradation("depth", "DEPTH_INVALID_BOOK")

        self.books[instrument_token] = {
            "depth": depth,
            "imbalance": res.imbalance,
            "depth_state": res.depth_state,
            "is_valid": res.is_valid,
            "buy_qty": res.buy_qty,
            "sell_qty": res.sell_qty,
            "spread": res.spread,
            "ts": now_epoch,
            "ts_epoch": now_epoch,
            "ts_iso": now_iso,
        }
        try:
            should_persist = self._should_persist_snapshot(instrument_token, now_epoch)
            with self._persist_lock:
                if should_persist:
                    self._sample_windows += 1
                else:
                    self._coalesced_updates += 1
            if should_persist:
                with self._persist_lock:
                    if self._persist_shutdown:
                        self._persist_pre_enqueue_rejected += 1
                        self._persist_degraded = True
                        record_degradation("depth", "DEPTH_PERSISTENCE_SHUTDOWN")
                        shutdown_rejected = True
                    else:
                        shutdown_rejected = False
                if shutdown_rejected:
                    self._record_rejection(reason_code="SHUTDOWN_REJECT", instrument_token=instrument_token,
                                           receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
                    return
                try:
                    canonical_depth = canonicalize_kite_depth(depth)
                    item_bytes = depth_queue_item_bytes(now_iso, instrument_token, canonical_depth, imbalance)
                except ValueError:
                    # Legacy callers may provide a compact partial book.  The
                    # WebSocket protocol owner remains strict; this store
                    # accepts the legacy shape only when its serialized
                    # envelope still fits the same byte bound.
                    canonical_depth = depth
                    item_bytes = len(json.dumps({"depth": depth, "imbalance": imbalance}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")) + 110
                require_item_size(item_bytes, MAX_DEPTH_QUEUE_ITEM_BYTES, "DEPTH_QUEUE")
                try:
                    # Apply bounded, time-limited backpressure without stalling the
                    # live WebSocket ingestion callback loop.
                    put_timeout_sec = min(0.05, max(0.0, float(
                        getattr(cfg, "DEPTH_PERSIST_QUEUE_PUT_TIMEOUT_SEC", 0.05) or 0.05)))
                    item = (now_iso, instrument_token,
                            json.dumps({"depth": canonical_depth, "imbalance": imbalance, "depth_state": res.depth_state, "is_valid": res.is_valid}, sort_keys=True, separators=(",", ":"), allow_nan=False), now_epoch)
                    # Hold admission serialization through enqueue + ledger update so
                    # the worker cannot dequeue an item before it is counted.
                    deadline = time.monotonic() + put_timeout_sec
                    while True:
                        with self._persist_admission_lock:
                            with self._persist_lock:
                                shutdown_rejected = self._persist_shutdown
                                if shutdown_rejected:
                                    self._persist_pre_enqueue_rejected += 1
                                    self._persist_degraded = True
                                    record_degradation("depth", "DEPTH_PERSISTENCE_SHUTDOWN")
                            if shutdown_rejected:
                                break
                            try:
                                self._persist_queue.put_nowait(item)
                            except queue.Full:
                                pass
                            else:
                                with self._persist_lock:
                                    self._persist_enqueued += 1
                                self._persist_wakeup.set()
                                break

                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise queue.Full
                        # Wait on Queue's own condition without holding the
                        # admission lock, allowing the worker to dequeue.
                        with self._persist_queue.not_full:
                            if self._persist_queue._qsize() >= self._persist_queue.maxsize:
                                self._persist_queue.not_full.wait(timeout=remaining)
                except queue.Full:
                    with self._persist_lock:
                        self._persist_pre_enqueue_rejected += 1
                        self._persist_degraded = True
                        record_degradation("depth", "DEPTH_QUEUE_FULL")
                    self._record_rejection(reason_code="QUEUE_REJECTED", instrument_token=instrument_token,
                                           receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
                    logger.error("depth_persistence_queue_full")
                else:
                    if shutdown_rejected:
                        self._record_rejection(reason_code="SHUTDOWN_REJECT", instrument_token=instrument_token,
                                               receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
            # alert on spikes (optional)
            if getattr(cfg, "IMBALANCE_ALERT_ENABLE", False):
                if abs(imbalance) > getattr(cfg, "IMBALANCE_ALERT", 0.6):
                    from core.telegram_alerts import send_telegram_message
                    send_telegram_message(f"Depth imbalance spike {imbalance:.2f} for token {instrument_token}")
        except (StorageBoundViolation, ValueError, TypeError) as exc:
            with self._persist_lock:
                self._persist_pre_enqueue_rejected += 1
                self._persist_degraded = True
            record_degradation("depth", "DEPTH_BOUND_REJECTED")
            self._record_rejection(reason_code="BOUND_REJECTED", instrument_token=instrument_token, receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
            logger.warning("depth_persistence_bound_rejected error=%s", type(exc).__name__)
        except Exception as exc:
            if str(exc) not in {"", "depth persistence is shut down"}:
                try:
                    self._record_rejection(reason_code="UNKNOWN_REJECTION", instrument_token=instrument_token, receipt_epoch=now_epoch, queue_depth=self._persist_queue.qsize())
                except Exception:
                    with self._persist_lock:
                        self._persist_provenance_write_failures += 1
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
        sampling_interval_sec = self._sampling_interval_sec()
        with self._persist_admission_lock:
            with self._persist_lock:
                qsize = self._persist_queue.qsize()
                enqueued = self._persist_enqueued
                in_flight = self._persist_in_flight
                persisted = self._persisted
                queue_rejected = self._persist_queue_rejected
                pre_enqueue_rejected = self._persist_pre_enqueue_rejected
                total_rejected = queue_rejected + pre_enqueue_rejected
                failures = self._persist_failures
                unaccounted = enqueued - (persisted + in_flight + qsize + queue_rejected + failures)
                total_attempts = enqueued + pre_enqueue_rejected
                return {
                "capture_mode": str(getattr(reliability_cfg, "DEPTH_CAPTURE_MODE", "UNKNOWN")),
                "depth_input_count": self._raw_updates_seen,
                "depth_accepted_count": self._persist_enqueued,
                "depth_persisted_count": self._persisted,
                "depth_rejected_count": total_rejected,
                "depth_duplicate_count": None,
                "depth_duplicate_count_status": "UNAVAILABLE_NO_STABLE_EVENT_ID",
                "raw_updates_seen": self._raw_updates_seen,
                "sample_windows": self._sample_windows,
                "snapshots_persisted": self._persisted,
                "coalesced_updates": self._coalesced_updates,
                "sampling_interval_ms": int(sampling_interval_sec * 1000),
                "sampling_interval_config_valid": not self._sampling_interval_config_invalid,
                "queue_depth": qsize,
                "in_flight": in_flight,
                "enqueued": enqueued,
                "admission_attempts": total_attempts,
                "persisted": persisted,
                "rejected": total_rejected,
                "queue_rejected": queue_rejected,
                "pre_enqueue_rejected": pre_enqueue_rejected,
                "failures": self._persist_failures,
                "provenance_write_failures": self._persist_provenance_write_failures,
                "unaccounted_remainder": unaccounted,
                "accounting_invariant_ok": (unaccounted == 0),
                "admission_accounting_invariant_ok": (
                    total_attempts == persisted + in_flight + qsize + queue_rejected + failures + pre_enqueue_rejected
                ),
                "durability_degraded": self._persist_degraded,
                "shutdown": self._persist_shutdown,
                "worker_alive": self._persist_thread.is_alive(),
                }

    def persistence_accounting(self) -> dict:
        """Expose institutional-grade accounting invariant metrics."""
        return self.persistence_state()

    def request_persistence_shutdown(self) -> None:
        """Close depth-write admission and wake the worker without waiting."""
        with self._persist_admission_lock:
            with self._persist_lock:
                self._persist_shutdown = True
        self._persist_wakeup.set()
        self._persist_stop.set()

    def shutdown_persistence(self, deadline_seconds: float = 2.0) -> dict:
        self.request_persistence_shutdown()
        deadline = time.monotonic() + max(0.0, float(deadline_seconds))
        while self._persist_queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
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
