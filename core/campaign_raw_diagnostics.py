"""Bounded campaign-only pre-decode and callback diagnostics."""

from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import queue
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


_IST = ZoneInfo("Asia/Kolkata")
_QUEUE: queue.Queue[dict] = queue.Queue(maxsize=256)
_RECENT = deque(maxlen=128)
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_STOP = threading.Event()
_LAST_SAMPLE = 0.0
_STATE = {
    "raw_message_count": 0,
    "binary_message_count": 0,
    "text_message_count": 0,
    "raw_byte_count": 0,
    "on_ticks_entry_count": 0,
    "on_ticks_exit_count": 0,
    "on_ticks_exception_count": 0,
    "on_ticks_inflight": 0,
    "decoded_tick_count": 0,
    "store_insert_success_count": 0,
    "store_insert_failure_count": 0,
    "last_raw_message_monotonic_ns": None,
    "last_on_ticks_entry_monotonic_ns": None,
    "last_on_ticks_exit_monotonic_ns": None,
    "maximum_callback_duration_ms": 0.0,
    "queue_drop_count": 0,
}


def _enabled() -> bool:
    return str(os.getenv("UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE", "")).lower() in {"1", "true", "yes", "on"}


def _identity() -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": os.getenv("UNIFIED_LIVE_VALIDATION_PR748_756_RUN_ID"),
        "session_date": os.getenv("UNIFIED_LIVE_VALIDATION_PR748_756_SESSION_DATE"),
        "campaign_commit_sha": os.getenv("UNIFIED_LIVE_VALIDATION_PR748_756_COMMIT_SHA"),
        "process_id": os.getpid(),
        "thread_name": threading.current_thread().name,
        "feed_session_id": None,
        "reconnect_generation": None,
        "subscription_generation": None,
        "connection_id": None,
    }


def _enqueue(path: str, payload: dict) -> None:
    try:
        _QUEUE.put_nowait({"path": path, "payload": payload})
    except queue.Full:
        with _LOCK:
            _STATE["queue_drop_count"] += 1


def _writer() -> None:
    while not _STOP.is_set() or not _QUEUE.empty():
        try:
            item = _QUEUE.get(timeout=0.1)
        except queue.Empty:
            continue
        try:
            root = Path(os.getenv("UNIFIED_LIVE_VALIDATION_PR748_756_EVIDENCE_ROOT", ""))
            path = root / "live" / item["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item["payload"], sort_keys=True, default=str) + "\n")
        finally:
            _QUEUE.task_done()


def start() -> bool:
    global _THREAD
    if not _enabled():
        return False
    with _LOCK:
        if _THREAD is None or not _THREAD.is_alive():
            _STOP.clear()
            _THREAD = threading.Thread(target=_writer, name="campaign-diagnostic-writer", daemon=True)
            _THREAD.start()
    return True


def observe_raw_message(payload: object, is_binary: bool) -> None:
    if not _enabled():
        return
    start()
    now = time.monotonic_ns()
    with _LOCK:
        previous = _STATE.get("last_raw_message_monotonic_ns")
        _STATE["raw_message_count"] += 1
        _STATE["binary_message_count"] += int(bool(is_binary))
        _STATE["text_message_count"] += int(not is_binary)
        _STATE["raw_byte_count"] += len(payload) if isinstance(payload, (bytes, bytearray, str)) else 0
        _STATE["last_raw_message_monotonic_ns"] = now
        _RECENT.append(now)
    _sample("raw_message", previous)


def on_ticks_entry(batch_size: int) -> int | None:
    if not _enabled():
        return None
    start()
    now = time.monotonic_ns()
    with _LOCK:
        _STATE["on_ticks_entry_count"] += 1
        _STATE["on_ticks_inflight"] += 1
        _STATE["last_on_ticks_entry_monotonic_ns"] = now
        _STATE["decoded_tick_count"] += int(batch_size)
    _sample("on_ticks_entry", None)
    return now


def on_ticks_exit(start_ns: int | None, *, exception: bool = False) -> None:
    if not _enabled():
        return
    now = time.monotonic_ns()
    with _LOCK:
        _STATE["on_ticks_exit_count"] += 1
        _STATE["on_ticks_inflight"] = max(0, int(_STATE["on_ticks_inflight"]) - 1)
        _STATE["on_ticks_exception_count"] += int(exception)
        _STATE["last_on_ticks_exit_monotonic_ns"] = now
        if start_ns is not None:
            _STATE["maximum_callback_duration_ms"] = max(
                float(_STATE["maximum_callback_duration_ms"]), (now - start_ns) / 1_000_000.0
            )
    _sample("on_ticks_exit", None)


def _sample(event: str, previous_ns: int | None) -> None:
    global _LAST_SAMPLE
    now = time.monotonic()
    if now - _LAST_SAMPLE < 1.0 and event != "on_ticks_exit":
        return
    _LAST_SAMPLE = now
    with _LOCK:
        payload = {**_identity(), **_STATE, "event_type": event, "monotonic_ns": time.monotonic_ns(),
                   "queue_depth": _QUEUE.qsize(), "queue_capacity": _QUEUE.maxsize}
        if previous_ns is not None:
            payload["intermessage_gap_ms"] = (payload["monotonic_ns"] - previous_ns) / 1_000_000.0
    _enqueue("predecode_raw_message_timeline.jsonl", payload)
    _enqueue("callback_execution_timeline.jsonl", payload)


def shutdown() -> None:
    if _THREAD is None:
        return
    _STOP.set()
    _THREAD.join(timeout=2.0)


__all__ = ["observe_raw_message", "on_ticks_entry", "on_ticks_exit", "shutdown", "start"]
