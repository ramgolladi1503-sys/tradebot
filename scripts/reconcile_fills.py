from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import argparse
import json

import pandas as pd

from core.paths import logs_dir
from core.reconciliation import reconcile_execution_fills
from core.trade_log_paths import resolve_trade_log_path


LOG_PATH = resolve_trade_log_path()
UPDATES_PATH = logs_dir() / "trade_updates.jsonl"
OUT_CSV = logs_dir() / "reconciliation_report.csv"
OUT_JSON = logs_dir() / "reconciliation_summary.json"
OUT_HIST = logs_dir() / "reconciliation_history.json"


def _append_history(summary: dict) -> None:
    history = []
    if OUT_HIST.exists():
        try:
            history = json.loads(OUT_HIST.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append(
        {
            "ts": pd.Timestamp.now(tz="UTC").isoformat(),
            "match_rate": float(summary.get("match_rate") or 0.0),
        }
    )
    OUT_HIST.parent.mkdir(parents=True, exist_ok=True)
    OUT_HIST.write_text(json.dumps(history[-1000:], indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile executed trades from canonical EXECUTION_FILL events.")
    parser.add_argument(
        "--date",
        default=None,
        help="Optional exchange-local date (YYYY-MM-DD). If omitted, all available execution fill events are used.",
    )
    args = parser.parse_args()

    rows, summary = reconcile_execution_fills(trade_date=args.date)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    _append_history(summary)

    if summary.get("error"):
        print(f"[reconcile_fills][ERROR] {summary.get('error')}")
    if summary.get("warning"):
        print(f"[reconcile_fills][WARN] {summary.get('warning')}")
    print(json.dumps(summary, sort_keys=True))
    print("reconcile_fills wrote:", OUT_JSON, OUT_CSV, OUT_HIST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
