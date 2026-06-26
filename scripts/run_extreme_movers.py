from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
from typing import Sequence

from core.analytics.daily_intel import load_day_events
from core.analytics.extreme_movers import build_extreme_movers_table, write_outputs


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run offline Extreme Movers reverse-engineering analytics."
    )
    parser.add_argument("--day", required=True, help="Target day in YYYY-MM-DD.")
    parser.add_argument(
        "--base",
        default="runtime/analytics",
        help="Analytics base directory (default: runtime/analytics).",
    )
    parser.add_argument(
        "--top-k", type=int, default=10, help="Top movers per side (default: 10)."
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=1,
        help="Trailing day window used for input loading (default: 1).",
    )
    parser.add_argument(
        "--trigger-pct",
        type=float,
        default=0.30,
        help="Trigger percent for T0 detection (default: 0.30).",
    )
    parser.add_argument(
        "--lookback-min",
        type=int,
        default=30,
        help="Pre-move lookback window in minutes (default: 30).",
    )
    parser.add_argument(
        "--horizon-min",
        type=int,
        default=45,
        help="Replay horizon in minutes (default: 45).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    target_day = date.fromisoformat(str(args.day))
    base = Path(args.base)
    top_k = max(1, int(args.top_k))
    window_days = max(1, int(args.window_days))

    events = load_day_events(base, target_day, window_days=window_days)
    rows = build_extreme_movers_table(
        events,
        target_day,
        top_k=top_k,
        trigger_pct=float(args.trigger_pct),
        lookback_min=max(1, int(args.lookback_min)),
        horizon_min=max(1, int(args.horizon_min)),
    )
    md_path, json_path = write_outputs(rows, base / "reports" / target_day.isoformat())

    print(
        json.dumps(
            {
                "day": target_day.isoformat(),
                "rows_loaded": len(events),
                "movers_count": len(rows),
                "extreme_movers_markdown_path": str(md_path),
                "extreme_movers_json_path": str(json_path),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
