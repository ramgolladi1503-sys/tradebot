from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class EventLogState:
    seen_event_ids: set[str] = field(default_factory=set)
    seen_trade_ids: set[str] = field(default_factory=set)
    unique_events: list[dict[str, Any]] = field(default_factory=list)
    duplicate_count: int = 0


def _validate(path: Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {
            "ok": True,
            "bad_lines": 0,
            "truncated_tail": False,
            "last_good_offset": 0,
            "file_size": 0,
        }

    file_size = int(target.stat().st_size)
    bad_lines = 0
    truncated_tail = False
    last_good_offset = 0
    offset = 0

    with target.open("rb") as handle:
        for raw in handle:
            offset += len(raw)
            line = raw.strip()
            if not line:
                last_good_offset = offset
                continue
            try:
                decoded = line.decode("utf-8")
                row = json.loads(decoded)
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
        "bad_lines": int(bad_lines),
        "truncated_tail": bool(truncated_tail),
        "last_good_offset": int(last_good_offset),
        "file_size": int(file_size),
    }


def validate_and_repair(path: Path) -> dict[str, Any]:
    target = Path(path)
    validation = _validate(target)
    repaired = False
    bytes_trimmed = 0

    if target.exists() and bool(validation.get("truncated_tail")):
        raw = target.read_bytes()
        keep = int(validation.get("last_good_offset") or 0)
        repaired_raw = raw[:keep]
        bytes_trimmed = max(0, len(raw) - len(repaired_raw))
        if bytes_trimmed > 0:
            tmp = target.with_suffix(target.suffix + f".tmp.{os.getpid()}")
            with tmp.open("wb") as handle:
                handle.write(repaired_raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
            repaired = True
            validation = _validate(target)

    return {
        "path": str(target),
        "ok": bool(validation.get("ok", True)),
        "bad_lines": int(validation.get("bad_lines", 0)),
        "truncated_tail": bool(validation.get("truncated_tail", False)),
        "last_good_offset": int(validation.get("last_good_offset", 0)),
        "repaired": bool(repaired),
        "bytes_trimmed": int(bytes_trimmed),
    }


def iter_events(path: Path) -> Iterator[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return
    with target.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = str(line).strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if isinstance(row, dict):
                yield row


def build_state_from_events(path: Path) -> EventLogState:
    state = EventLogState()
    seen_trade_event_keys: set[tuple[str, str]] = set()
    seen_fallback_keys: set[tuple[str, str]] = set()

    for row in iter_events(path):
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        event_type = str(row.get("type") or "").strip()

        event_id = str(payload.get("event_id") or row.get("event_id") or "").strip()
        if event_id:
            if event_id in state.seen_event_ids:
                state.duplicate_count += 1
                continue
            state.seen_event_ids.add(event_id)

        trade_id = str(payload.get("trade_id") or row.get("trade_id") or "").strip()
        if trade_id:
            dedupe_key = (trade_id, event_type or "-")
            if dedupe_key in seen_trade_event_keys:
                state.duplicate_count += 1
                continue
            seen_trade_event_keys.add(dedupe_key)
            state.seen_trade_ids.add(trade_id)
        else:
            fallback_key = (event_type or "-", json.dumps(payload, sort_keys=True, default=str))
            if fallback_key in seen_fallback_keys:
                state.duplicate_count += 1
                continue
            seen_fallback_keys.add(fallback_key)

        state.unique_events.append(row)

    return state
