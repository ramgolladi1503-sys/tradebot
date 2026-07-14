from __future__ import annotations

import collections
import dataclasses
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

TRACE_EVERY_N = max(1, int(os.environ.get("TRADEBOT_FEED_FD_TRACE_EVERY_N", "1000")))
TRACE_FD_DELTA_THRESHOLD = max(1, int(os.environ.get("TRADEBOT_FEED_FD_TRACE_DELTA", "5")))
TRACE_FD_BASELINE_HIGH = max(1, int(os.environ.get("TRADEBOT_FEED_FD_TRACE_HIGH", "20")))
TRACE_ENABLED = str(os.environ.get("TRADEBOT_FEED_FD_TRACE", "")).strip().lower() in {"1", "true", "yes", "on"}
TRACE_FULL_INVENTORY_ENABLED = str(os.environ.get("TRADEBOT_FEED_FD_TRACE_FULL", "")).strip().lower() in {"1", "true", "yes", "on"}

_TRACE_LOCK = threading.Lock()
_TRACE_COUNTER = 0
_TRACE_BASELINE_FD: int | None = None
_TRACE_LAST_FD: int | None = None
_TRACE_PATH: Path | None = Path(os.environ.get("TRADEBOT_FEED_FD_TRACE_PATH", "")).expanduser() if os.environ.get("TRADEBOT_FEED_FD_TRACE_PATH") else None
_TRACE_LOCAL = threading.local()


def reset_trace(*, baseline_fd: int | None = None, path: str | os.PathLike[str] | None = None) -> None:
    global _TRACE_COUNTER, _TRACE_BASELINE_FD, _TRACE_LAST_FD, _TRACE_PATH
    with _TRACE_LOCK:
        _TRACE_COUNTER = 0
        _TRACE_BASELINE_FD = baseline_fd
        _TRACE_LAST_FD = baseline_fd
        if path is not None:
            _TRACE_PATH = Path(path)


def process_fd_count() -> int | None:
    for candidate in (Path("/dev/fd"), Path("/proc/self/fd")):
        try:
            return len(list(candidate.iterdir()))
        except Exception:
            continue
    return None


def thread_count() -> int:
    return len(threading.enumerate())


def logger_handler_inventory() -> list[dict[str, Any]]:
    import logging

    handlers: list[dict[str, Any]] = []
    for name, obj in logging.Logger.manager.loggerDict.items():
        if isinstance(obj, logging.Logger):
            for handler in obj.handlers:
                handlers.append(
                    {
                        "logger": name,
                        "handler_type": type(handler).__name__,
                        "filename": getattr(handler, "baseFilename", None),
                        "closed": getattr(handler, "_closed", None),
                    }
                )
    root = logging.getLogger()
    for handler in root.handlers or []:
        handlers.append(
            {
                "logger": "root",
                "handler_type": type(handler).__name__,
                "filename": getattr(handler, "baseFilename", None),
                "closed": getattr(handler, "_closed", None),
            }
        )
    return handlers


def logger_handler_count() -> int:
    import logging

    return len(logger_handler_inventory()) + len(list(logging.getLogger().handlers or []))


def fd_type_counts() -> dict[str, int]:
    pid = str(os.getpid())
    try:
        proc = subprocess.run(["lsof", "-nP", "-p", pid], capture_output=True, text=True, check=False)
    except Exception as exc:
        return {"error": 1, "message": 1 if str(exc) else 0}
    counts: dict[str, int] = collections.Counter()
    for line in (proc.stdout or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) > 4:
            counts[parts[4]] += 1
    return dict(counts)


def descriptor_inventory(limit: int = 50) -> list[dict[str, str]]:
    pid = str(os.getpid())
    try:
        proc = subprocess.run(["lsof", "-nP", "-p", pid], capture_output=True, text=True, check=False)
    except Exception as exc:
        return [{"error": str(exc)}]
    rows: list[dict[str, str]] = []
    for line in (proc.stdout or "").splitlines()[1:]:
        parts = line.split(None, 8)
        if len(parts) < 9:
            continue
        rows.append(
            {
                "command": parts[0],
                "pid": parts[1],
                "user": parts[2],
                "fd": parts[3],
                "type": parts[4],
                "device": parts[5],
                "size_off": parts[6],
                "node": parts[7],
                "name": parts[8],
            }
        )
        if len(rows) >= limit:
            break
    return rows


@dataclasses.dataclass(frozen=True)
class FDTraceEvent:
    stage: str
    row_index: int | None
    callback_count: int
    fd_count: int | None
    fd_delta_from_baseline: int | None
    fd_delta_from_previous: int | None
    thread_count: int
    handler_count: int
    queue_depth: int | None
    pending_writes: int | None
    runtime_store_writes: int | None
    open_regular_files: int | None
    fd_types: dict[str, int] | None
    extra: dict[str, Any]


def should_sample(*, row_index: int | None, fd_count: int | None, baseline_fd: int | None = None) -> bool:
    if not TRACE_ENABLED:
        return False
    if row_index is not None and row_index % TRACE_EVERY_N == 0:
        return True
    baseline = baseline_fd if baseline_fd is not None else _TRACE_BASELINE_FD
    return fd_count is not None and baseline is not None and fd_count - baseline >= TRACE_FD_DELTA_THRESHOLD


def _open_regular_file_count() -> int | None:
    pid = str(os.getpid())
    try:
        proc = subprocess.run(["lsof", "-nP", "-p", pid], capture_output=True, text=True, check=False)
    except Exception:
        return None
    count = 0
    for line in (proc.stdout or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) > 4 and parts[4] == "REG":
            count += 1
    return count


def record_trace(
    stage: str,
    *,
    row_index: int | None = None,
    queue_depth: int | None = None,
    pending_writes: int | None = None,
    runtime_store_writes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> FDTraceEvent | None:
    if not TRACE_ENABLED or getattr(_TRACE_LOCAL, "active", False):
        return None
    fd_count = process_fd_count()
    with _TRACE_LOCK:
        global _TRACE_COUNTER, _TRACE_BASELINE_FD, _TRACE_LAST_FD
        _TRACE_COUNTER += 1
        if _TRACE_BASELINE_FD is None and fd_count is not None:
            _TRACE_BASELINE_FD = fd_count
        baseline = _TRACE_BASELINE_FD
        previous = _TRACE_LAST_FD
        if not should_sample(row_index=row_index, fd_count=fd_count, baseline_fd=baseline) and not (
            fd_count is not None and baseline is not None and fd_count >= baseline + TRACE_FD_BASELINE_HIGH
        ):
            _TRACE_LAST_FD = fd_count if fd_count is not None else _TRACE_LAST_FD
            return None
        event = FDTraceEvent(
            stage=stage,
            row_index=row_index,
            callback_count=_TRACE_COUNTER,
            fd_count=fd_count,
            fd_delta_from_baseline=(fd_count - baseline) if (fd_count is not None and baseline is not None) else None,
            fd_delta_from_previous=(fd_count - previous) if (fd_count is not None and previous is not None) else None,
            thread_count=thread_count(),
            handler_count=logger_handler_count(),
            queue_depth=queue_depth,
            pending_writes=pending_writes,
            runtime_store_writes=runtime_store_writes,
            open_regular_files=None,
            fd_types=None,
            extra=dict(extra or {}),
        )
        if (
            TRACE_FULL_INVENTORY_ENABLED
            and event.fd_count is not None
            and baseline is not None
            and event.fd_count >= baseline + TRACE_FD_BASELINE_HIGH
        ):
            event = dataclasses.replace(
                event,
                open_regular_files=_open_regular_file_count(),
                fd_types=fd_type_counts(),
                extra={**event.extra, "descriptor_inventory": descriptor_inventory(), "logger_handlers": logger_handler_inventory()},
            )
        _write_event(event)
        _TRACE_LAST_FD = fd_count if fd_count is not None else _TRACE_LAST_FD
        return event


def _write_event(event: FDTraceEvent) -> None:
    if _TRACE_PATH is None:
        return
    payload = dataclasses.asdict(event)
    try:
        _TRACE_LOCAL.active = True
        _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
            f.flush()
    finally:
        _TRACE_LOCAL.active = False
