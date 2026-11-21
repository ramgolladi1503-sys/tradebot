"""Level-2 Order Book Recorder & Parquet Logger.

Autonomous, thread-safe asynchronous recorder for live Level-2/Level-5 order book depth.
Features:
- Sub-second non-blocking capture of full 5-level market depth.
- In-memory bounded queue with fail-closed backpressure monitoring.
- Asynchronous batch flushing to Snappy-compressed Parquet files.
- Disk quota safety guard (halts before disk exhaustion).
- Microstructure feature transformation pipeline for incremental ML training.

Strict Trading Safety Invariants:
- read_only = True
- is_order_action = False
- broker_api_called = False
- allowed_for_live_execution = False
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from core.microstructure_features import (
    Level5BookSnapshot,
    MicrostructureFeatures,
    extract_microstructure_features,
)
from core.upstox_stream_broadcaster import (
    StreamSubscriber,
    StreamStatusEvent,
    UpstoxLevel5DepthRecord,
    UpstoxTickRecord,
    UPSTOX_LEVEL5_PARQUET_SCHEMA,
    QueueSaturationError,
)

logger = logging.getLogger(__name__)

# Disk safety threshold: halt recording if available disk space is below 1.0 GB
MIN_FREE_DISK_BYTES = 1024 * 1024 * 1024  # 1 GB


class DiskSpaceExhaustionError(RuntimeError):
    """Raised when available disk space falls below safe operating limits."""


class OrderBookL2Recorder(StreamSubscriber):
    """Production Level-2 Order Book Stream Recorder and Microstructure Pipeline."""

    def __init__(
        self,
        output_dir: str | Path,
        max_queue_size: int = 50_000,
        chunk_size: int = 1_000,
        flush_interval_sec: float = 1.0,
        min_free_bytes: int = MIN_FREE_DISK_BYTES,
        enable_feature_extraction: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_queue_size = int(max_queue_size)
        self.chunk_size = int(chunk_size)
        self.flush_interval_sec = float(flush_interval_sec)
        self.min_free_bytes = int(min_free_bytes)
        self.enable_feature_extraction = bool(enable_feature_extraction)

        self._queue: queue.Queue[UpstoxLevel5DepthRecord | None] = queue.Queue(
            maxsize=self.max_queue_size
        )
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._chunk_index = 0
        self._total_records_written = 0
        self._lock = threading.Lock()
        self._written_files: list[Path] = []
        self._feature_callbacks: list[Callable[[MicrostructureFeatures], None]] = []

        # Strict safety invariants
        self.read_only = True
        self.is_order_action = False
        self.broker_api_called = False
        self.allowed_for_live_execution = False

        self._check_disk_space()
        self._start_worker()

    def _check_disk_space(self) -> None:
        """Verify underlying filesystem has sufficient free space."""
        total, used, free = shutil.disk_usage(self.output_dir)
        if free < self.min_free_bytes:
            raise DiskSpaceExhaustionError(
                f"Disk space critical: {free / (1024*1024):.1f} MB free, minimum required is {self.min_free_bytes / (1024*1024):.1f} MB"
            )

    def _start_worker(self) -> None:
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="L2OrderBookRecorderWorker",
            daemon=True,
        )
        self._worker_thread.start()

    def add_feature_callback(self, cb: Callable[[MicrostructureFeatures], None]) -> None:
        """Register real-time consumer for derived microstructure features."""
        self._feature_callbacks.append(cb)

    def on_tick(self, tick: UpstoxTickRecord) -> None:
        """Tick event - depth recorder processes L5 depth events."""
        pass

    def on_stream_status(self, status: StreamStatusEvent) -> None:
        """Stream status telemetry."""
        pass

    def on_depth(self, depth: UpstoxLevel5DepthRecord) -> None:
        """Non-blocking sub-second ingest with fail-closed backpressure."""
        try:
            self._queue.put_nowait(depth)
        except queue.Full:
            logger.critical(
                "L2 Recorder queue saturated at %d records. Invoking fail-closed halt.",
                self.max_queue_size,
            )
            raise QueueSaturationError(
                f"L2 Recorder queue saturated at capacity {self.max_queue_size}. Fail closed."
            )

    def stop(self, timeout: float = 5.0) -> None:
        """Gracefully stop worker and drain all remaining in-memory buffers."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    @property
    def total_records_written(self) -> int:
        with self._lock:
            return self._total_records_written

    @property
    def written_files(self) -> list[Path]:
        with self._lock:
            return list(self._written_files)

    def _worker_loop(self) -> None:
        buffer: list[UpstoxLevel5DepthRecord] = []
        last_flush_time = time.monotonic()

        while not self._stop_event.is_set():
            try:
                timeout = min(0.1, max(0.01, self.flush_interval_sec - (time.monotonic() - last_flush_time)))
                record = self._queue.get(timeout=timeout)
                if record is not None:
                    buffer.append(record)
                    if self.enable_feature_extraction and self._feature_callbacks:
                        self._dispatch_features(record)
                self._queue.task_done()
            except queue.Empty:
                pass

            now = time.monotonic()
            if len(buffer) >= self.chunk_size or (buffer and (now - last_flush_time) >= self.flush_interval_sec):
                self._flush_chunk(buffer)
                buffer = []
                last_flush_time = time.monotonic()

        # Final drain of remaining queue items
        while not self._queue.empty():
            try:
                record = self._queue.get_nowait()
                if record is not None:
                    buffer.append(record)
                    if self.enable_feature_extraction and self._feature_callbacks:
                        self._dispatch_features(record)
                self._queue.task_done()
            except queue.Empty:
                break

        if buffer:
            self._flush_chunk(buffer)

    def _dispatch_features(self, record: UpstoxLevel5DepthRecord) -> None:
        """Derive stationary microstructure features and notify callbacks."""
        snapshot = Level5BookSnapshot(
            token=record.token,
            exchange_timestamp_ms=record.exchange_timestamp_ms,
            ltp=record.ltp,
            bid_prices=(record.bid_p1, record.bid_p2, record.bid_p3, record.bid_p4, record.bid_p5),
            bid_quantities=(record.bid_q1, record.bid_q2, record.bid_q3, record.bid_q4, record.bid_q5),
            ask_prices=(record.ask_p1, record.ask_p2, record.ask_p3, record.ask_p4, record.ask_p5),
            ask_quantities=(record.ask_q1, record.ask_q2, record.ask_q3, record.ask_q4, record.ask_q5),
        )
        features = extract_microstructure_features(snapshot)
        for cb in self._feature_callbacks:
            try:
                cb(features)
            except Exception:
                logger.exception("Error in microstructure feature callback")

    def _flush_chunk(self, buffer: list[UpstoxLevel5DepthRecord]) -> None:
        if not buffer:
            return

        self._check_disk_space()

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
            filename = self.output_dir / f"orderbook_l2_chunk_{self._chunk_index:05d}.parquet"
            pq.write_table(table, filename, compression="snappy")
            self._written_files.append(filename)
            self._total_records_written += len(buffer)
