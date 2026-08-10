"""Independent validators for unified campaign artifacts."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from core.unified_live_validation_pr748_756.campaign_contract import READ_ONLY_FLAGS


FORBIDDEN_PREOUTCOME_FIELDS = (
    "future",
    "forward",
    "next",
    "entry",
    "exit",
    "outcome",
    "target",
    "label",
    "pnl",
    "profit",
    "payoff",
    "winner",
    "holdout",
)


def validate_jsonl_file(path: Path, *, expected_run_id: str | None = None) -> dict[str, Any]:
    malformed = 0
    rows = 0
    bad_run_id = 0
    unsafe_rows = 0
    first_ts = None
    last_ts = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                malformed += 1
                continue
            rows += 1
            if expected_run_id is not None and row.get("run_id") != expected_run_id:
                bad_run_id += 1
            if any(row.get(key) is not value for key, value in READ_ONLY_FLAGS.items()):
                unsafe_rows += 1
            ts = row.get("source_timestamp") or row.get("receipt_timestamp")
            if ts is not None:
                first_ts = ts if first_ts is None else min(first_ts, ts)
                last_ts = ts if last_ts is None else max(last_ts, ts)
    return {
        "path": str(path),
        "rows": rows,
        "malformed_rows": malformed,
        "bad_run_id_rows": bad_run_id,
        "unsafe_rows": unsafe_rows,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "pass": malformed == 0 and bad_run_id == 0 and unsafe_rows == 0,
    }


def scan_preoutcome_fields(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in row:
        lowered = key.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_PREOUTCOME_FIELDS):
            out.append(key)
    return sorted(out)

