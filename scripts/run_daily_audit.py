"""Migration note:
Daily audit degrades to explicit SKIPPED when required decision/truth data is
not available, so batch ops do not hard-fail on fresh installs.
"""

import argparse
import json
import sys
from pathlib import Path
from core.time_utils import now_ist
from core.paths import data_root, logs_dir

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.truth_dataset import build_truth_dataset
from core.reports.daily_audit import build_daily_audit
from core.reports.execution_report import build_execution_report
from core.reports.decay_report import build_decay_report
from core.reports.rl_shadow_report import build_rl_shadow_report


def _status_paths(day: str) -> tuple[Path, Path]:
    log_root = logs_dir()
    return log_root / f"daily_audit_status_{day}.json", log_root / "daily_audit_status_latest.json"


def _write_status(payload: dict) -> Path:
    day = str(payload.get("date") or now_ist().strftime("%Y-%m-%d"))
    day_path, latest_path = _status_paths(day)
    body = json.dumps(payload, indent=2, default=str)
    day_path.parent.mkdir(parents=True, exist_ok=True)
    day_path.write_text(body, encoding="utf-8")
    latest_path.write_text(body, encoding="utf-8")
    return day_path


def _return_ok_with_skips(day: str, reason_code: str, detail: str | None = None) -> dict:
    payload = {
        "status": "ok_with_skips",
        "date": day,
        "reason_code": str(reason_code),
        "reason": str(reason_code),  # Backward-compatible alias.
    }
    if detail:
        payload["detail"] = str(detail)
    status_path = _write_status(payload)
    if detail:
        print(f"[daily_audit][INFO] {reason_code}: {detail}")
    else:
        print(f"[daily_audit][INFO] {reason_code}")
    print(f"[daily_audit][INFO] status=ok_with_skips status_file={status_path}")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Run daily audit reports.")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD date (default: today).")
    parser.add_argument("--truth", default=str(data_root() / "truth_dataset.parquet"), help="Truth dataset parquet path.")
    args = parser.parse_args()

    day = args.date or now_ist().strftime("%Y-%m-%d")
    truth_path = Path(args.truth)
    if not truth_path.exists():
        try:
            build_truth_dataset(out_parquet=truth_path)
        except FileNotFoundError as exc:
            reason = "NO_DECISION_EVENTS"
            return _return_ok_with_skips(day, reason, detail=str(exc))

    if not truth_path.exists():
        reason = "SHADOW_ROWS_INSUFFICIENT"
        return _return_ok_with_skips(day, reason, detail=str(truth_path))

    try:
        df = pd.read_parquet(truth_path)
    except Exception as exc:
        reason = "TRUTH_DATASET_UNREADABLE"
        return _return_ok_with_skips(day, reason, detail=f"{truth_path} ({exc})")
    if df.empty:
        reason = "TRUTH_DATASET_EMPTY"
        return _return_ok_with_skips(day, reason, detail=str(truth_path))

    audit_path = logs_dir() / f"daily_audit_{day}.json"
    exec_path = logs_dir() / f"execution_report_{day}.json"
    decay_path = logs_dir() / f"decay_report_{day}.json"
    rl_path = logs_dir() / f"rl_shadow_report_{day}.json"

    build_daily_audit(df, day, audit_path)
    build_execution_report(df, day, exec_path)
    build_decay_report(day, decay_path)
    build_rl_shadow_report(df, day, rl_path)

    print(f"Daily audit: {audit_path}")
    print(f"Execution report: {exec_path}")
    print(f"Decay report: {decay_path}")
    print(f"RL shadow report: {rl_path}")
    payload = {
        "status": "ok",
        "date": day,
        "reason_code": "OK",
        "reason": "OK",
        "artifacts": {
            "daily_audit": str(audit_path),
            "execution_report": str(exec_path),
            "decay_report": str(decay_path),
            "rl_shadow_report": str(rl_path),
        },
    }
    status_path = _write_status(payload)
    print(f"[daily_audit][INFO] status=ok status_file={status_path}")
    return payload


if __name__ == "__main__":
    main()
