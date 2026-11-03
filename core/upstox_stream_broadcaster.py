from __future__ import annotations

import datetime as dt
import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Exceptions & Events
# -------------------------------------------------------------------------

class QueueSaturationError(RuntimeError):
    """Raised when the persistence queue reaches full capacity (fail-closed)."""


@dataclass(slots=True, frozen=True)
class StreamStatusEvent:
    event: str
    details: dict[str, Any]
    timestamp_utc: str


# -------------------------------------------------------------------------
# Dataclasses
# -------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class UpstoxLevel5DepthRecord:
    token: str
    symbol: str
    exchange_timestamp_ms: int        # Upstox source exchange timestamp
    ingress_monotonic_ns: int         # Local monotonic ns at socket receipt
    ingress_wall_utc: str             # Local wall clock UTC ISO-8601
    sequence_id: int                  # Monotonic per-token sequence number
    ltp: float
    volume: int
    open_interest: int
    # 5-Level Bid Array
    bid_p1: float; bid_q1: int; bid_o1: int
    bid_p2: float; bid_q2: int; bid_o2: int
    bid_p3: float; bid_q3: int; bid_o3: int
    bid_p4: float; bid_q4: int; bid_o4: int
    bid_p5: float; bid_q5: int; bid_o5: int
    # 5-Level Ask Array
    ask_p1: float; ask_q1: int; ask_o1: int
    ask_p2: float; ask_q2: int; ask_o2: int
    ask_p3: float; ask_q3: int; ask_o3: int
    ask_p4: float; ask_q4: int; ask_o4: int
    ask_p5: float; ask_q5: int; ask_o5: int


@dataclass(slots=True, frozen=True)
class UpstoxTickRecord:
    token: str
    symbol: str
    exchange_timestamp_ms: int
    ingress_monotonic_ns: int
    ingress_wall_utc: str
    sequence_id: int
    ltp: float
    volume: int
    open_interest: int
    best_bid: float
    best_ask: float


# -------------------------------------------------------------------------
# PyArrow Schema
# -------------------------------------------------------------------------

UPSTOX_LEVEL5_PARQUET_SCHEMA = pa.schema([
    ("token", pa.string()),
    ("symbol", pa.string()),
    ("exchange_timestamp_ms", pa.int64()),
    ("ingress_monotonic_ns", pa.int64()),
    ("ingress_wall_utc", pa.string()),
    ("sequence_id", pa.int64()),
    ("ltp", pa.float64()),
    ("volume", pa.int64()),
    ("open_interest", pa.int64()),
    # Bids Level 1-5
    ("bid_p1", pa.float64()), ("bid_q1", pa.int64()), ("bid_o1", pa.int32()),
    ("bid_p2", pa.float64()), ("bid_q2", pa.int64()), ("bid_o2", pa.int32()),
    ("bid_p3", pa.float64()), ("bid_q3", pa.int64()), ("bid_o3", pa.int32()),
    ("bid_p4", pa.float64()), ("bid_q4", pa.int64()), ("bid_o4", pa.int32()),
    ("bid_p5", pa.float64()), ("bid_q5", pa.int64()), ("bid_o5", pa.int32()),
    # Asks Level 1-5
    ("ask_p1", pa.float64()), ("ask_q1", pa.int64()), ("ask_o1", pa.int32()),
    ("ask_p2", pa.float64()), ("ask_q2", pa.int64()), ("ask_o2", pa.int32()),
    ("ask_p3", pa.float64()), ("ask_q3", pa.int64()), ("ask_o3", pa.int32()),
    ("ask_p4", pa.float64()), ("ask_q4", pa.int64()), ("ask_o4", pa.int32()),
    ("ask_p5", pa.float64()), ("ask_q5", pa.int64()), ("ask_o5", pa.int32()),
])


# -------------------------------------------------------------------------
# Stream Subscriber Protocol
# -------------------------------------------------------------------------

class StreamSubscriber(Protocol):
    def on_tick(self, tick: UpstoxTickRecord) -> None: ...
    def on_depth(self, depth: UpstoxLevel5DepthRecord) -> None: ...
    def on_stream_status(self, status: StreamStatusEvent) -> None: ...


# -------------------------------------------------------------------------
# UpstoxAsyncParquetRecorder
# -------------------------------------------------------------------------

class UpstoxAsyncParquetRecorder:
    """Dedicated background persistence worker with bounded queue.
    
    Flushes typed Level-5 PyArrow tables to rolling Parquet chunks and supports
    post-session stitching.
    """

    def __init__(
        self,
        output_dir: str | Path,
        max_queue_size: int = 10_000,
        watermark_ratio: float = 0.80,
        chunk_size: int = 1000,
        flush_interval_sec: float = 1.0,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_queue_size = int(max_queue_size)
        self.watermark_threshold = int(self.max_queue_size * watermark_ratio)
        self.chunk_size = int(chunk_size)
        self.flush_interval_sec = float(flush_interval_sec)

        self._queue: queue.Queue[UpstoxLevel5DepthRecord | None] = queue.Queue(
            maxsize=self.max_queue_size
        )
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._chunk_index = 0
        self._written_files: list[Path] = []
        self._total_records_written = 0
        self._lock = threading.Lock()
        self._telemetry_callbacks: list[Any] = []
        self._high_watermark_emitted = False

        # Trading safety indicators
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False

        self._start_worker()

    def add_telemetry_callback(self, cb: Any) -> None:
        self._telemetry_callbacks.append(cb)

    def _emit_telemetry(self, event_name: str, details: dict[str, Any]) -> None:
        event = {
            "event": event_name,
            "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            **details,
        }
        for cb in self._telemetry_callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Error in recorder telemetry callback")

    def _start_worker(self) -> None:
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="UpstoxPersistenceWorkerThread",
            daemon=True,
        )
        self._worker_thread.start()

    def on_tick(self, tick: UpstoxTickRecord) -> None:
        """Ticks can optionally be recorded or ignored if recorder targets L5 depth."""
        pass

    def on_depth(self, depth: UpstoxLevel5DepthRecord) -> None:
        """Enqueue Level-5 depth record with strict fail-closed policy."""
        q_size = self._queue.qsize()

        if q_size >= self.watermark_threshold:
            if not self._high_watermark_emitted:
                self._high_watermark_emitted = True
                self._emit_telemetry(
                    "QUEUE_HIGH_WATERMARK",
                    {
                        "queue_size": q_size,
                        "capacity": self.max_queue_size,
                        "watermark_ratio": q_size / self.max_queue_size,
                    },
                )
        else:
            self._high_watermark_emitted = False

        try:
            self._queue.put_nowait(depth)
        except queue.Full:
            self._emit_telemetry(
                "PERSISTENCE_QUEUE_EXHAUSTED",
                {
                    "queue_size": self._queue.qsize(),
                    "capacity": self.max_queue_size,
                    "action": "FAIL_CLOSED_HALT",
                },
            )
            raise QueueSaturationError(
                f"Persistence queue saturated at full capacity {self.max_queue_size}. Fail closed."
            )

    def on_stream_status(self, status: StreamStatusEvent) -> None:
        pass

    def _worker_loop(self) -> None:
        buffer: list[UpstoxLevel5DepthRecord] = []
        last_flush_time = time.monotonic()

        while True:
            # Drain as many items as currently available without long wait
            try:
                # If stop event is set and queue is empty, break out
                if self._stop_event.is_set() and self._queue.empty():
                    break
                timeout = min(0.1, max(0.01, self.flush_interval_sec - (time.monotonic() - last_flush_time)))
                item = self._queue.get(timeout=timeout)
                if item is not None:
                    buffer.append(item)
                self._queue.task_done()
            except queue.Empty:
                if self._stop_event.is_set():
                    break

            # Drain any further pending items in queue quickly into buffer
            while len(buffer) < self.chunk_size:
                try:
                    item = self._queue.get_nowait()
                    if item is not None:
                        buffer.append(item)
                    self._queue.task_done()
                except queue.Empty:
                    break

            now = time.monotonic()
            should_flush = (
                len(buffer) >= self.chunk_size
                or (buffer and (now - last_flush_time) >= self.flush_interval_sec)
                or (self._stop_event.is_set() and buffer)
            )

            if should_flush:
                self._flush_buffer(buffer)
                buffer = []
                last_flush_time = time.monotonic()

        # Final drain of queue and buffer
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                if item is not None:
                    buffer.append(item)
                self._queue.task_done()
            except queue.Empty:
                break

        if buffer:
            self._flush_buffer(buffer)

    def _flush_buffer(self, buffer: list[UpstoxLevel5DepthRecord]) -> None:
        if not buffer:
            return

        cols: dict[str, list[Any]] = {field.name: [] for field in UPSTOX_LEVEL5_PARQUET_SCHEMA}

        for rec in buffer:
            cols["token"].append(rec.token)
            cols["symbol"].append(rec.symbol)
            cols["exchange_timestamp_ms"].append(rec.exchange_timestamp_ms)
            cols["ingress_monotonic_ns"].append(rec.ingress_monotonic_ns)
            cols["ingress_wall_utc"].append(rec.ingress_wall_utc)
            cols["sequence_id"].append(rec.sequence_id)
            cols["ltp"].append(rec.ltp)
            cols["volume"].append(rec.volume)
            cols["open_interest"].append(rec.open_interest)

            cols["bid_p1"].append(rec.bid_p1); cols["bid_q1"].append(rec.bid_q1); cols["bid_o1"].append(rec.bid_o1)
            cols["bid_p2"].append(rec.bid_p2); cols["bid_q2"].append(rec.bid_q2); cols["bid_o2"].append(rec.bid_o2)
            cols["bid_p3"].append(rec.bid_p3); cols["bid_q3"].append(rec.bid_q3); cols["bid_o3"].append(rec.bid_o3)
            cols["bid_p4"].append(rec.bid_p4); cols["bid_q4"].append(rec.bid_q4); cols["bid_o4"].append(rec.bid_o4)
            cols["bid_p5"].append(rec.bid_p5); cols["bid_q5"].append(rec.bid_q5); cols["bid_o5"].append(rec.bid_o5)

            cols["ask_p1"].append(rec.ask_p1); cols["ask_q1"].append(rec.ask_q1); cols["ask_o1"].append(rec.ask_o1)
            cols["ask_p2"].append(rec.ask_p2); cols["ask_q2"].append(rec.ask_q2); cols["ask_o2"].append(rec.ask_o2)
            cols["ask_p3"].append(rec.ask_p3); cols["ask_q3"].append(rec.ask_q3); cols["ask_o3"].append(rec.ask_o3)
            cols["ask_p4"].append(rec.ask_p4); cols["ask_q4"].append(rec.ask_q4); cols["ask_o4"].append(rec.ask_o4)
            cols["ask_p5"].append(rec.ask_p5); cols["ask_q5"].append(rec.ask_q5); cols["ask_o5"].append(rec.ask_o5)

        table = pa.Table.from_pydict(cols, schema=UPSTOX_LEVEL5_PARQUET_SCHEMA)

        with self._lock:
            self._chunk_index += 1
            filename = self.output_dir / f"level5_chunk_{self._chunk_index:05d}.parquet"
            # PyArrow write_table releases GIL during C++ Parquet encoding and disk write
            self._write_parquet(filename, table)
            self._written_files.append(filename)
            self._total_records_written += len(buffer)

    def _write_parquet(self, path: Path, table: pa.Table) -> None:
        """Hook method for testing disk I/O stall isolation."""
        pq.write_table(table, path, compression="snappy")

    def flush_and_stop(self, timeout: float = 30.0) -> None:
        """Stops worker and flushes remaining queue records."""
        self._stop_event.set()
        if self._worker_thread is not None and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    @property
    def written_files(self) -> list[Path]:
        with self._lock:
            return list(self._written_files)

    @property
    def total_records_written(self) -> int:
        with self._lock:
            return self._total_records_written

    def stitch_chunks(self, output_path: str | Path) -> Path:
        """Stitches all written chunk Parquet files into a single master Parquet file."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            files = list(self._written_files)
        if not files:
            empty_table = pa.Table.from_batches([], schema=UPSTOX_LEVEL5_PARQUET_SCHEMA)
            pq.write_table(empty_table, out, compression="snappy")
            return out

        tables = [pq.read_table(f) for f in files]
        master = pa.concat_tables(tables)
        pq.write_table(master, out, compression="snappy")
        return out


# -------------------------------------------------------------------------
# UpstoxStreamBroadcaster
# -------------------------------------------------------------------------

class UpstoxStreamBroadcaster:
    """Ingress fan-out producer that delivers decoded ticks/Level-5 depth to
    registered in-memory listeners and asynchronous persistence recorder.
    """

    def __init__(self, subscribers: list[StreamSubscriber] | None = None) -> None:
        self._subscribers: list[StreamSubscriber] = list(subscribers) if subscribers else []
        self._sequence_counters: dict[str, int] = {}
        self._lock = threading.Lock()

        # Strict safety invariants
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False

    def add_subscriber(self, subscriber: StreamSubscriber) -> None:
        with self._lock:
            self._subscribers.append(subscriber)

    def _next_sequence_id(self, token: str) -> int:
        with self._lock:
            curr = self._sequence_counters.get(token, 0) + 1
            self._sequence_counters[token] = curr
            return curr

    def dispatch_tick(
        self,
        raw_feed: dict[str, Any],
        now_ns: int | None = None,
        now_utc: str | None = None,
    ) -> UpstoxTickRecord:
        """Decode and broadcast a tick record."""
        ingress_monotonic_ns = time.monotonic_ns() if now_ns is None else now_ns
        ingress_wall_utc = (
            dt.datetime.now(dt.timezone.utc).isoformat() if now_utc is None else now_utc
        )

        token = str(raw_feed.get("token") or raw_feed.get("instrument_key") or "")
        symbol = str(raw_feed.get("symbol") or token)
        seq_id = self._next_sequence_id(token)

        exchange_ts = int(
            raw_feed.get("exchange_timestamp_ms")
            or raw_feed.get("source_ts_epoch_ms")
            or raw_feed.get("currentTs")
            or 0
        )
        ltp = float(raw_feed.get("ltp") or 0.0)
        volume = int(raw_feed.get("volume") or 0)
        open_interest = int(raw_feed.get("open_interest") or raw_feed.get("oi") or 0)
        best_bid = float(raw_feed.get("best_bid") or raw_feed.get("bid_price") or 0.0)
        best_ask = float(raw_feed.get("best_ask") or raw_feed.get("ask_price") or 0.0)

        record = UpstoxTickRecord(
            token=token,
            symbol=symbol,
            exchange_timestamp_ms=exchange_ts,
            ingress_monotonic_ns=ingress_monotonic_ns,
            ingress_wall_utc=ingress_wall_utc,
            sequence_id=seq_id,
            ltp=ltp,
            volume=volume,
            open_interest=open_interest,
            best_bid=best_bid,
            best_ask=best_ask,
        )

        with self._lock:
            subs = list(self._subscribers)

        for sub in subs:
            try:
                sub.on_tick(record)
            except Exception:
                logger.exception("Error dispatching tick to subscriber")

        return record

    def dispatch_depth(
        self,
        raw_feed: dict[str, Any],
        now_ns: int | None = None,
        now_utc: str | None = None,
    ) -> UpstoxLevel5DepthRecord:
        """Decode and broadcast a Level-5 depth record."""
        ingress_monotonic_ns = time.monotonic_ns() if now_ns is None else now_ns
        ingress_wall_utc = (
            dt.datetime.now(dt.timezone.utc).isoformat() if now_utc is None else now_utc
        )

        token = str(raw_feed.get("token") or raw_feed.get("instrument_key") or "")
        symbol = str(raw_feed.get("symbol") or token)
        seq_id = self._next_sequence_id(token)

        exchange_ts = int(
            raw_feed.get("exchange_timestamp_ms")
            or raw_feed.get("source_ts_epoch_ms")
            or raw_feed.get("currentTs")
            or 0
        )
        ltp = float(raw_feed.get("ltp") or 0.0)
        volume = int(raw_feed.get("volume") or 0)
        open_interest = int(raw_feed.get("open_interest") or raw_feed.get("oi") or 0)

        # Depth extraction (support direct fields or depth list)
        depth_list = raw_feed.get("depth")
        if depth_list and isinstance(depth_list, list):
            bids = []
            asks = []
            for lvl in depth_list:
                bp = float(lvl.get("bid_price") or lvl.get("bidP") or 0.0)
                bq = int(lvl.get("bid_quantity") or lvl.get("bidQ") or 0)
                bo = int(lvl.get("bid_orders") or lvl.get("bidO") or 0)
                ap = float(lvl.get("ask_price") or lvl.get("askP") or 0.0)
                aq = int(lvl.get("ask_quantity") or lvl.get("askQ") or 0)
                ao = int(lvl.get("ask_orders") or lvl.get("askO") or 0)
                bids.append((bp, bq, bo))
                asks.append((ap, aq, ao))

            while len(bids) < 5:
                bids.append((0.0, 0, 0))
            while len(asks) < 5:
                asks.append((0.0, 0, 0))

            (bp1, bq1, bo1), (bp2, bq2, bo2), (bp3, bq3, bo3), (bp4, bq4, bo4), (bp5, bq5, bo5) = bids[:5]
            (ap1, aq1, ao1), (ap2, aq2, ao2), (ap3, aq3, ao3), (ap4, aq4, ao4), (ap5, aq5, ao5) = asks[:5]
        else:
            bp1 = float(raw_feed.get("bid_p1", 0.0)); bq1 = int(raw_feed.get("bid_q1", 0)); bo1 = int(raw_feed.get("bid_o1", 0))
            bp2 = float(raw_feed.get("bid_p2", 0.0)); bq2 = int(raw_feed.get("bid_q2", 0)); bo2 = int(raw_feed.get("bid_o2", 0))
            bp3 = float(raw_feed.get("bid_p3", 0.0)); bq3 = int(raw_feed.get("bid_q3", 0)); bo3 = int(raw_feed.get("bid_o3", 0))
            bp4 = float(raw_feed.get("bid_p4", 0.0)); bq4 = int(raw_feed.get("bid_q4", 0)); bo4 = int(raw_feed.get("bid_o4", 0))
            bp5 = float(raw_feed.get("bid_p5", 0.0)); bq5 = int(raw_feed.get("bid_q5", 0)); bo5 = int(raw_feed.get("bid_o5", 0))

            ap1 = float(raw_feed.get("ask_p1", 0.0)); aq1 = int(raw_feed.get("ask_q1", 0)); ao1 = int(raw_feed.get("ask_o1", 0))
            ap2 = float(raw_feed.get("ask_p2", 0.0)); aq2 = int(raw_feed.get("ask_q2", 0)); ao2 = int(raw_feed.get("ask_o2", 0))
            ap3 = float(raw_feed.get("ask_p3", 0.0)); aq3 = int(raw_feed.get("ask_q3", 0)); ao3 = int(raw_feed.get("ask_o3", 0))
            ap4 = float(raw_feed.get("ask_p4", 0.0)); aq4 = int(raw_feed.get("ask_q4", 0)); ao4 = int(raw_feed.get("ask_o4", 0))
            ap5 = float(raw_feed.get("ask_p5", 0.0)); aq5 = int(raw_feed.get("ask_q5", 0)); ao5 = int(raw_feed.get("ask_o5", 0))

        record = UpstoxLevel5DepthRecord(
            token=token,
            symbol=symbol,
            exchange_timestamp_ms=exchange_ts,
            ingress_monotonic_ns=ingress_monotonic_ns,
            ingress_wall_utc=ingress_wall_utc,
            sequence_id=seq_id,
            ltp=ltp,
            volume=volume,
            open_interest=open_interest,
            bid_p1=bp1, bid_q1=bq1, bid_o1=bo1,
            bid_p2=bp2, bid_q2=bq2, bid_o2=bo2,
            bid_p3=bp3, bid_q3=bq3, bid_o3=bo3,
            bid_p4=bp4, bid_q4=bq4, bid_o4=bo4,
            bid_p5=bp5, bid_q5=bq5, bid_o5=bo5,
            ask_p1=ap1, ask_q1=aq1, ask_o1=ao1,
            ask_p2=ap2, ask_q2=aq2, ask_o2=ao2,
            ask_p3=ap3, ask_q3=aq3, ask_o3=ao3,
            ask_p4=ap4, ask_q4=aq4, ask_o4=ao4,
            ask_p5=ap5, ask_q5=aq5, ask_o5=ao5,
        )

        with self._lock:
            subs = list(self._subscribers)

        for sub in subs:
            try:
                sub.on_depth(record)
            except Exception:
                logger.exception("Error dispatching depth to subscriber")

        return record
