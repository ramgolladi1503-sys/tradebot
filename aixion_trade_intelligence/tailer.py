from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import os

from .storage import atomic_write_json


class TailerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TailCheckpoint:
    source_path: str
    device: int
    inode: int
    offset: int
    line_number: int
    prefix_sha256: str
    tail_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TailRecord:
    row: dict[str, Any]
    line_number: int
    offset_start: int
    offset_end: int
    line_sha256: str


class JsonlTailer:
    """Checkpointed JSONL tailer with truncation and rotation detection.

    Checkpoints advance only after a complete line is decoded. A partial final
    line remains unread until the producer completes it. A bounded prefix hash
    detects in-place rewrites where inode and file size are unchanged.
    """

    _FINGERPRINT_BYTES = 4096

    def __init__(
        self,
        source_path: str | Path,
        checkpoint_path: str | Path,
        *,
        max_line_bytes: int = 4_000_000,
    ) -> None:
        if max_line_bytes <= 0:
            raise ValueError("max_line_bytes must be positive")
        self.source_path = Path(source_path)
        self.checkpoint_path = Path(checkpoint_path)
        self.max_line_bytes = int(max_line_bytes)

    def _prefix_hash(self, offset: int) -> str:
        length = min(max(0, offset), self._FINGERPRINT_BYTES)
        if length == 0:
            return sha256(b"").hexdigest()
        with self.source_path.open("rb") as handle:
            return sha256(handle.read(length)).hexdigest()

    def _load_checkpoint(self) -> TailCheckpoint | None:
        if not self.checkpoint_path.exists():
            return None
        try:
            raw = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
            return TailCheckpoint(
                source_path=str(raw["source_path"]),
                device=int(raw["device"]),
                inode=int(raw["inode"]),
                offset=int(raw["offset"]),
                line_number=int(raw["line_number"]),
                prefix_sha256=str(raw.get("prefix_sha256") or ""),
                tail_sha256=str(raw.get("tail_sha256") or ""),
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise TailerError(f"invalid checkpoint {self.checkpoint_path}: {exc}") from exc

    def _tail_hash(self, offset: int) -> str:
        if offset <= 0:
            return sha256(b"").hexdigest()
        length = min(offset, self._FINGERPRINT_BYTES)
        with self.source_path.open("rb") as handle:
            handle.seek(offset - length)
            return sha256(handle.read(length)).hexdigest()

    def _write_checkpoint(
        self,
        *,
        stat: os.stat_result,
        offset: int,
        line_number: int,
    ) -> None:
        checkpoint = TailCheckpoint(
            source_path=str(self.source_path.resolve()),
            device=stat.st_dev,
            inode=stat.st_ino,
            offset=offset,
            line_number=line_number,
            prefix_sha256=self._prefix_hash(offset),
            tail_sha256=self._tail_hash(offset),
        )
        atomic_write_json(self.checkpoint_path, checkpoint.to_dict())

    def _initial_position(self, stat: os.stat_result) -> tuple[int, int]:
        checkpoint = self._load_checkpoint()
        if checkpoint is None:
            return 0, 0
        same_file = checkpoint.device == stat.st_dev and checkpoint.inode == stat.st_ino
        not_truncated = stat.st_size >= checkpoint.offset
        prefix_matches = (
            not checkpoint.prefix_sha256
            or checkpoint.prefix_sha256 == self._prefix_hash(checkpoint.offset)
        )
        tail_matches = (
            not checkpoint.tail_sha256
            or checkpoint.tail_sha256 == self._tail_hash(checkpoint.offset)
        )
        if same_file and not_truncated and prefix_matches and tail_matches:
            return checkpoint.offset, checkpoint.line_number
        return 0, 0

    def read_available(self, *, limit: int | None = None) -> tuple[TailRecord, ...]:
        if not self.source_path.exists():
            return ()
        stat = self.source_path.stat()
        offset, line_number = self._initial_position(stat)
        records: list[TailRecord] = []
        committed_offset = offset
        committed_line = line_number
        with self.source_path.open("rb") as handle:
            handle.seek(offset)
            while limit is None or len(records) < limit:
                line_start = handle.tell()
                line = handle.readline(self.max_line_bytes + 1)
                if not line:
                    break
                if len(line) > self.max_line_bytes:
                    self._write_checkpoint(stat=stat, offset=committed_offset, line_number=committed_line)
                    raise TailerError(f"line exceeds max_line_bytes at offset {line_start}")
                if not line.endswith(b"\n"):
                    break
                line_end = handle.tell()
                next_line_number = committed_line + 1
                stripped = line.strip()
                if not stripped:
                    committed_offset = line_end
                    committed_line = next_line_number
                    continue
                try:
                    decoded = stripped.decode("utf-8")
                    raw = json.loads(decoded)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    self._write_checkpoint(stat=stat, offset=committed_offset, line_number=committed_line)
                    raise TailerError(
                        f"invalid JSONL at {self.source_path}:{next_line_number} offset {line_start}: {exc}"
                    ) from exc
                if not isinstance(raw, dict):
                    self._write_checkpoint(stat=stat, offset=committed_offset, line_number=committed_line)
                    raise TailerError(
                        f"JSONL row must be an object at {self.source_path}:{next_line_number}"
                    )
                records.append(
                    TailRecord(
                        row=raw,
                        line_number=next_line_number,
                        offset_start=line_start,
                        offset_end=line_end,
                        line_sha256=sha256(stripped).hexdigest(),
                    )
                )
                committed_offset = line_end
                committed_line = next_line_number
        self._write_checkpoint(stat=stat, offset=committed_offset, line_number=committed_line)
        return tuple(records)
