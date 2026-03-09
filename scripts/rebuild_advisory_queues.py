#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from core.review_queue import (
    TARGET_POINTS_QUEUE_PATH,
    ZERO_HERO_QUEUE_PATH,
    load_queue_rows,
    write_queue_rows,
)


_STALE_ENTRY_STATUSES = {
    "STALE_OPTION_LTP",
    "STALE_PRICE",
    "INVALID_LTP",
    "NO_TOKEN",
    "NO_LIVE_OPTION_FEED",
}
_TERMINAL_STATUSES = {"ACTIVE", "RESOLVED", "EXITED", "CANCELLED"}


def _normalize_status(value: object) -> str:
    return str(value or "").strip().upper()


def _coerce_epoch(value: object) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out > 1e12:
            out = out / 1000.0
        return out
    except Exception:
        pass
    try:
        text = str(value or "").strip()
        if not text:
            return None
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _row_ts_epoch(row: dict) -> float | None:
    for key in ("timestamp_epoch", "ts_epoch", "last_seen_epoch", "updated_epoch"):
        ts = _coerce_epoch((row or {}).get(key))
        if ts is not None:
            return ts
    for key in ("timestamp", "ts_ist", "last_seen_ts", "updated_ts"):
        ts = _coerce_epoch((row or {}).get(key))
        if ts is not None:
            return ts
    return None


def _rebuild_rows(
    rows: list[dict],
    *,
    clear_stale_entry: bool,
    prune_age_min: int | None = None,
    now_epoch: float | None = None,
) -> tuple[list[dict], dict[str, int]]:
    out: list[dict] = []
    now_ts = float(now_epoch if now_epoch is not None else time.time())
    max_age_sec = None
    if prune_age_min is not None:
        try:
            max_age_sec = max(60.0, float(prune_age_min) * 60.0)
        except Exception:
            max_age_sec = None
    stats = {
        "rows_in": len(rows),
        "rows_out": 0,
        "stale_entries_cleared": 0,
        "status_reset_to_planning": 0,
        "aged_rows_dropped": 0,
    }
    for row in rows:
        record = dict(row or {})
        lifecycle = _normalize_status(record.get("status"))
        entry_status = _normalize_status(record.get("entry_status"))

        if clear_stale_entry and entry_status in _STALE_ENTRY_STATUSES and lifecycle not in _TERMINAL_STATUSES:
            if record.get("entry") not in (None, "", "None"):
                record["entry"] = None
                stats["stale_entries_cleared"] += 1
            record["suggested_entry"] = None
            if _normalize_status(record.get("status")) != "PLANNING":
                record["status"] = "PLANNING"
                stats["status_reset_to_planning"] += 1

        if max_age_sec is not None and lifecycle not in _TERMINAL_STATUSES:
            ts_epoch = _row_ts_epoch(record)
            if ts_epoch is not None and (now_ts - float(ts_epoch)) > max_age_sec:
                stats["aged_rows_dropped"] += 1
                continue

        out.append(record)

    stats["rows_out"] = len(out)
    return out, stats


def _run_for_path(
    path: Path,
    *,
    dry_run: bool,
    clear_stale_entry: bool,
    prune_age_min: int | None,
) -> dict[str, object]:
    rows = load_queue_rows(path)
    rebuilt, stats = _rebuild_rows(rows, clear_stale_entry=clear_stale_entry, prune_age_min=prune_age_min)
    if not dry_run:
        write_queue_rows(path, rebuilt)
    return {
        "path": str(path),
        "dry_run": bool(dry_run),
        **stats,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild advisory queues and clear stale planned entries.")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing.")
    parser.add_argument(
        "--keep-stale-entry",
        action="store_true",
        help="Do not clear stale entry/suggested_entry values.",
    )
    parser.add_argument(
        "--prune-age-min",
        type=int,
        default=int(getattr(__import__("config.config", fromlist=["config"]).config, "QUEUE_ROW_MAX_AGE_MIN", 120)),
        help="Drop non-terminal rows older than this many minutes (default: cfg.QUEUE_ROW_MAX_AGE_MIN).",
    )
    args = parser.parse_args()

    clear_stale_entry = not bool(args.keep_stale_entry)
    prune_age_min = int(args.prune_age_min) if args.prune_age_min and int(args.prune_age_min) > 0 else None
    reports = [
        _run_for_path(
            TARGET_POINTS_QUEUE_PATH,
            dry_run=bool(args.dry_run),
            clear_stale_entry=clear_stale_entry,
            prune_age_min=prune_age_min,
        ),
        _run_for_path(
            ZERO_HERO_QUEUE_PATH,
            dry_run=bool(args.dry_run),
            clear_stale_entry=clear_stale_entry,
            prune_age_min=prune_age_min,
        ),
    ]
    print(json.dumps({"reports": reports}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
