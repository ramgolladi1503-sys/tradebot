from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from typing import Sequence

from core.analytics.daily_intel import build_day_report, load_day_events, write_day_outputs


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline daily intelligence aggregator.")
    parser.add_argument("--day", required=True, help="Target day in YYYY-MM-DD.")
    parser.add_argument("--base", default="runtime/analytics", help="Analytics base directory (default: runtime/analytics).")
    parser.add_argument("--window-days", type=int, default=1, help="Trailing day window size (default: 1).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    day = date.fromisoformat(str(args.day))
    base = Path(args.base)
    window_days = max(1, int(args.window_days))

    rows = load_day_events(base, day, window_days=window_days)
    report = build_day_report(rows, day)
    report["summary"]["window_days"] = window_days
    md_path, json_path, proposal_md_path, proposal_json_path = write_day_outputs(report, base / "reports")

    print(
        json.dumps(
            {
                "day": day.isoformat(),
                "window_days": window_days,
                "rows_loaded": len(rows),
                "daily_report_markdown_path": str(md_path),
                "daily_report_json_path": str(json_path),
                "config_delta_markdown_path": str(proposal_md_path),
                "config_delta_json_path": str(proposal_json_path),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
