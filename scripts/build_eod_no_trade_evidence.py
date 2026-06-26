#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import runpy

runpy.run_path(str(Path(__file__).with_name("bootstrap.py")))

from core.eod_no_trade_evidence import build_eod_no_trade_evidence, write_eod_no_trade_evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Build read-only EOD no-trade evidence from tick/replay/runtime artifacts.")
    parser.add_argument("--date", required=True, help="Trade date in YYYY-MM-DD format.")
    parser.add_argument("--tick-file", required=True, help="Raw tick JSONL file.")
    parser.add_argument("--replay-file", default="data/active_options_replay.json", help="Converted replay JSON file.")
    parser.add_argument("--runtime-dir", default=".runtime", help="Runtime artifact directory.")
    parser.add_argument("--wfa-csv", default="data/oos_trades.csv", help="Proxy WFA CSV path.")
    parser.add_argument("--json-out", required=True, help="Output JSON evidence path.")
    parser.add_argument("--markdown-out", required=True, help="Output Markdown evidence path.")
    args = parser.parse_args()

    evidence = build_eod_no_trade_evidence(
        trade_date=args.date,
        tick_path=args.tick_file,
        replay_path=args.replay_file,
        runtime_dir=args.runtime_dir,
        wfa_csv_path=args.wfa_csv,
    )
    json_path, markdown_path = write_eod_no_trade_evidence(
        evidence,
        json_path=args.json_out,
        markdown_path=args.markdown_out,
    )
    print(f"json: {json_path}")
    print(f"markdown: {markdown_path}")
    print(f"warnings: {len(evidence.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
