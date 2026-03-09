from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def validate_events_file(path: Path) -> dict[str, Any]:
    """
    Validate line-delimited JSON events file integrity.

    Returns:
      {
        "ok": bool,
        "bad_lines": int,
        "truncated_tail": bool,
        "last_good_offset": int,
      }
    """
    target = Path(path)
    if not target.exists():
        return {
            "ok": True,
            "bad_lines": 0,
            "truncated_tail": False,
            "last_good_offset": 0,
        }

    file_size = int(target.stat().st_size)
    bad_lines = 0
    truncated_tail = False
    last_good_offset = 0
    offset = 0

    with target.open("rb") as handle:
        for raw in handle:
            offset += len(raw)
            stripped = raw.strip()
            if not stripped:
                last_good_offset = offset
                continue
            try:
                row = json.loads(stripped.decode("utf-8"))
                if not isinstance(row, dict):
                    raise ValueError("event row must be a JSON object")
            except Exception:
                bad_lines += 1
                if offset >= file_size:
                    truncated_tail = True
                continue
            last_good_offset = offset

    return {
        "ok": bad_lines == 0,
        "bad_lines": bad_lines,
        "truncated_tail": truncated_tail,
        "last_good_offset": int(last_good_offset),
    }


def repair_events_file(path: Path) -> dict[str, Any]:
    """
    Repair only a truncated EOF tail by trimming bytes after last good event row.
    """
    target = Path(path)
    if not target.exists():
        return {"repaired": False, "bytes_trimmed": 0}

    validation = validate_events_file(target)
    if not bool(validation.get("truncated_tail")):
        return {"repaired": False, "bytes_trimmed": 0}

    last_good_offset = int(validation.get("last_good_offset") or 0)
    raw = target.read_bytes()
    repaired_raw = raw[:last_good_offset]
    bytes_trimmed = max(0, len(raw) - len(repaired_raw))
    if bytes_trimmed == 0:
        return {"repaired": False, "bytes_trimmed": 0}

    tmp = target.with_suffix(target.suffix + f".tmp.{os.getpid()}")
    with tmp.open("wb") as handle:
        handle.write(repaired_raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, target)
    return {"repaired": True, "bytes_trimmed": int(bytes_trimmed)}
