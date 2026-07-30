from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

_VOLATILE_KEYS = {
    "timestamp", "ts", "generated_at", "created_at", "updated_at",
    "latency_ms", "duration_ms", "cycle_id", "run_id",
}


def canonicalize(value: Any, *, volatile_keys: Iterable[str] = _VOLATILE_KEYS) -> Any:
    ignored = set(volatile_keys)
    if isinstance(value, Mapping):
        return {
            str(key): canonicalize(item, volatile_keys=ignored)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in ignored
        }
    if isinstance(value, (list, tuple)):
        return [canonicalize(item, volatile_keys=ignored) for item in value]
    if isinstance(value, float):
        return round(value, 10)
    return value


def canonical_bytes(value: Any, *, volatile_keys: Iterable[str] = _VOLATILE_KEYS) -> bytes:
    normalized = canonicalize(value, volatile_keys=volatile_keys)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def semantic_hash(value: Any, *, volatile_keys: Iterable[str] = _VOLATILE_KEYS) -> str:
    return hashlib.sha256(canonical_bytes(value, volatile_keys=volatile_keys)).hexdigest()


def load_snapshot_rows(path: str | Path) -> list[Any]:
    source = Path(path)
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if source.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    return payload if isinstance(payload, list) else [payload]


@dataclass(frozen=True)
class GoldenMasterResult:
    matched: bool
    expected_hash: str
    actual_hash: str
    expected_rows: int
    actual_rows: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "expected_rows": self.expected_rows,
            "actual_rows": self.actual_rows,
        }


def compare_snapshots(expected: Any, actual: Any) -> GoldenMasterResult:
    expected_rows = expected if isinstance(expected, list) else [expected]
    actual_rows = actual if isinstance(actual, list) else [actual]
    expected_hash = semantic_hash(expected_rows)
    actual_hash = semantic_hash(actual_rows)
    return GoldenMasterResult(
        matched=expected_hash == actual_hash,
        expected_hash=expected_hash,
        actual_hash=actual_hash,
        expected_rows=len(expected_rows),
        actual_rows=len(actual_rows),
    )


def compare_snapshot_files(expected_path: str | Path, actual_path: str | Path) -> GoldenMasterResult:
    return compare_snapshots(load_snapshot_rows(expected_path), load_snapshot_rows(actual_path))


__all__ = [
    "GoldenMasterResult", "canonicalize", "canonical_bytes", "semantic_hash",
    "load_snapshot_rows", "compare_snapshots", "compare_snapshot_files",
]
