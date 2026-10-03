"""Cross-process serialized append for newline-delimited JSON batches."""

from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
from typing import Iterable, Mapping, Any

logger = logging.getLogger(__name__)


def append_jsonl_batch(
    path: Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    ensure_ascii: bool = True,
) -> None:
    """Append a complete JSONL batch under an advisory process lock.

    Cooperating writers are serialized across the whole batch. On failure,
    never truncate the shared file: a non-cooperating writer can append between
    any size check and truncate because advisory locks cannot serialize it.
    Preserve all bytes, report the incomplete batch, and propagate the write
    failure. Downstream readers must surface an incomplete JSONL tail.
    """
    encoded = b"".join(
        (json.dumps(dict(row), sort_keys=True, ensure_ascii=ensure_ascii) + "\n").encode("utf-8")
        for row in rows
        if isinstance(row, Mapping)
    )
    if not encoded:
        return

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o666)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        written_total = 0
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("JSONL_APPEND_NO_PROGRESS")
                written_total += written
                view = view[written:]
        except BaseException as write_error:
            logger.error(
                "JSONL append failed; in-place rollback skipped to preserve concurrent bytes; "
                "path=%s own_bytes=%d",
                path,
                written_total,
                exc_info=(type(write_error), write_error, write_error.__traceback__),
            )
            raise
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
