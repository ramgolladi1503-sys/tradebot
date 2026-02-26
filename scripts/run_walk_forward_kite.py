from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import runpy
import sys

import pandas as pd

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.walk_forward import run_walk_forward
from scripts.build_walk_forward_input import build_walk_forward_input


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_input_output(symbol: str, interval: str) -> Path:
    clean_symbol = str(symbol).strip().upper() or "NIFTY"
    clean_interval = str(interval).strip().lower().replace(" ", "_")
    return Path("data") / f"{clean_symbol}_{clean_interval}_walk_forward.csv"


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(
        description="Fetch historical candles from Kite and run walk-forward in one command."
    )
    parser.add_argument("--symbol", default="NIFTY")
    parser.add_argument("--interval", default="5minute")
    parser.add_argument("--lookback-days", type=int, default=180)
    parser.add_argument("--chunk-days", type=int, default=60)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--input-output", default="", help="Output CSV path for fetched candles")
    parser.add_argument("--train-window-days", type=int, default=60)
    parser.add_argument("--test-window-days", type=int, default=10)
    parser.add_argument("--step-days", type=int, default=10)
    parser.add_argument("--starting-capital", type=float, default=100000.0)
    parser.add_argument("--output-dir", default=".runtime/reports/walk_forward")
    args = parser.parse_args(argv)

    now_utc = datetime.now(timezone.utc)
    end_dt = _parse_dt(args.end) if str(args.end).strip() else now_utc
    start_dt = _parse_dt(args.start) if str(args.start).strip() else (
        end_dt - timedelta(days=max(1, int(args.lookback_days)))
    )
    input_output = (
        Path(str(args.input_output).strip())
        if str(args.input_output).strip()
        else _default_input_output(args.symbol, args.interval)
    )

    build_report = build_walk_forward_input(
        symbol=str(args.symbol).upper(),
        interval=str(args.interval),
        start_dt=start_dt,
        end_dt=end_dt,
        output_path=input_output,
        chunk_days=max(1, int(args.chunk_days)),
    )
    input_path = Path(build_report["output_path"])
    historical = pd.read_csv(input_path)
    summary = run_walk_forward(
        historical_data=historical,
        train_window_days=int(args.train_window_days),
        test_window_days=int(args.test_window_days),
        step_days=int(args.step_days),
        starting_capital=float(args.starting_capital),
        output_dir=str(args.output_dir),
        write_outputs=True,
    )
    artifacts = summary.get("artifacts", {})
    print("Walk-forward complete")
    print(f"Input CSV: {input_path}")
    print(f"Windows: {summary['config']['window_count']}")
    print(f"Avg return: {summary['aggregate']['avg_return']:.6f}")
    print(f"Total trades: {summary['aggregate']['total_trades']}")
    if artifacts:
        print(f"JSON: {artifacts.get('json')}")
        print(f"CSV: {artifacts.get('csv')}")
    return {"build_report": build_report, "summary": summary}


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[RUN_WF_KITE][ERROR] {type(exc).__name__}: {exc}")
        raise SystemExit(1)
