from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
import json
import os

from .contracts import CanonicalEvent, EventValidationError, canonical_json


class EvidenceReadError(RuntimeError):
    pass


def iter_events(path: str | Path) -> Iterator[CanonicalEvent]:
    evidence_path = Path(path)
    try:
        handle = evidence_path.open("r", encoding="utf-8")
    except OSError as exc:
        raise EvidenceReadError(f"cannot open evidence file {evidence_path}: {exc}") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield CanonicalEvent.from_json(line)
            except EventValidationError as exc:
                raise EvidenceReadError(f"{evidence_path}:{line_number}: {exc}") from exc


def load_events(path: str | Path) -> list[CanonicalEvent]:
    return list(iter_events(path))


def atomic_write_json(path: str | Path, value: Any) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(value) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=output_path.parent, delete=False) as temp:
        temp.write(payload)
        temp.flush()
        os.fsync(temp.fileno())
        temp_path = Path(temp.name)
    os.replace(temp_path, output_path)
    return output_path


def write_events(path: str | Path, events: Iterable[CanonicalEvent]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=output_path.parent, delete=False) as temp:
        for event in events:
            temp.write(event.to_json())
            temp.write("\n")
        temp.flush()
        os.fsync(temp.fileno())
        temp_path = Path(temp.name)
    os.replace(temp_path, output_path)
    return output_path


def export_parquet(path: str | Path, events: Iterable[CanonicalEvent]) -> Path:
    """Optional Parquet export using pyarrow when installed.

    JSONL remains the authoritative append-only evidence. Parquet is a derived
    analytical copy and failure to export must never change the raw evidence.
    """

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("pyarrow is required for Parquet export") from exc

    rows = [event.to_dict() for event in events]
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, output_path, compression="zstd")
    return output_path


def append_events(path: str | Path, events: Iterable[CanonicalEvent], *, fsync: bool = True) -> int:
    """Append a batch under one cross-process lock and return bytes written."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = b"".join((event.to_json() + "\n").encode("utf-8") for event in events)
    if not payload:
        return 0
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    fd = os.open(output_path, flags, 0o640)
    try:
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover
            fcntl = None
        total = 0
        view = memoryview(payload)
        while total < len(payload):
            written = os.write(fd, view[total:])
            if written <= 0:
                raise OSError("append returned no progress")
            total += written
        if fsync:
            os.fsync(fd)
    finally:
        if 'fcntl' in locals() and fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
    return total
