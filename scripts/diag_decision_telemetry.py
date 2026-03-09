#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from core.decision_telemetry_health import (
    check_decision_telemetry,
    decision_write_error_path,
)
from core.gate_status_log import gate_status_path
from core.telemetry_streams import decisions_stream_path
from core.time_utils import compute_age_sec, normalize_epoch_seconds, now_utc_epoch


def _scan_jsonl(path: Path, *, event_type: str | None = None) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "rows": 0, "last_ts_epoch": None, "last_age_sec": None}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {"path": str(path), "exists": True, "rows": 0, "last_ts_epoch": None, "last_age_sec": None}
    count = 0
    last_ts = None
    now_epoch = now_utc_epoch()
    for raw in lines:
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if event_type and str(payload.get("event_type") or "").strip().lower() != str(event_type).strip().lower():
            continue
        count += 1
        ts_val = normalize_epoch_seconds(payload.get("ts_epoch"))
        if ts_val is not None:
            last_ts = ts_val if (last_ts is None or ts_val > last_ts) else last_ts
    return {
        "path": str(path),
        "exists": True,
        "rows": count,
        "last_ts_epoch": last_ts,
        "last_age_sec": compute_age_sec(last_ts, now_epoch) if last_ts is not None else None,
    }


def _tail_errors(path: Path, *, limit: int = 3) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines[-limit:]:
        line = str(raw or "").strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            payload = {"raw": line}
        if isinstance(payload, dict):
            out.append(payload)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose decision telemetry stream health.")
    parser.add_argument("--desk", default="DEFAULT", help="Desk id (default: DEFAULT)")
    parser.add_argument("--max-age-sec", type=float, default=60.0, help="Freshness window for active decision telemetry.")
    args = parser.parse_args()

    desk = str(args.desk or "DEFAULT")
    decision_health = check_decision_telemetry(desk_id=desk, max_age_sec=float(args.max_age_sec))
    gate_stats = _scan_jsonl(gate_status_path(desk_id=desk))
    decision_stats = _scan_jsonl(decisions_stream_path(desk_id=desk), event_type="decision_evaluated")
    err_path = decision_write_error_path(desk_id=desk)
    errors = _tail_errors(err_path, limit=3)

    print(f"desk: {desk}")
    print(
        "decision_health:"
        f" ok={decision_health.get('ok')}"
        f" reason={decision_health.get('reason')}"
        f" recent={decision_health.get('decision_evaluated_recent')}"
        f" max_age_sec={decision_health.get('max_age_sec')}"
    )
    print(
        "gate_status:"
        f" rows={gate_stats.get('rows')}"
        f" last_ts={gate_stats.get('last_ts_epoch')}"
        f" last_age_sec={gate_stats.get('last_age_sec')}"
        f" path={gate_stats.get('path')}"
    )
    print(
        "decisions:"
        f" rows={decision_stats.get('rows')}"
        f" last_ts={decision_stats.get('last_ts_epoch')}"
        f" last_age_sec={decision_stats.get('last_age_sec')}"
        f" path={decision_stats.get('path')}"
    )
    print(f"decision_write_errors_path: {err_path}")
    if not errors:
        print("decision_write_errors_last3: []")
    else:
        print("decision_write_errors_last3:")
        for err in errors:
            print(json.dumps(err, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
