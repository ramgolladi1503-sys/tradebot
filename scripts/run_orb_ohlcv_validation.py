from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.orb_ohlcv_validation import run_orb_ohlcv_validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deterministic ORB OHLCV candle-research validation.")
    parser.add_argument("--candle-root", type=Path, required=True, help="Root of the historical candle corpus.")
    parser.add_argument("--manifest", type=Path, required=True, help="Deterministic session manifest JSON.")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path for the validation result.")
    parser.add_argument("--holding-minutes", type=int, default=15, help="Fixed research holding period in minutes.")
    parser.add_argument("--friction-bps", type=float, default=2.0, help="Round-trip friction in basis points.")
    parser.add_argument(
        "--entry-model",
        choices=("next_bar_open", "signal_bar_close_proxy"),
        default="next_bar_open",
        help="Research entry timing model.",
    )
    parser.add_argument(
        "--overlap-policy",
        choices=("non_overlapping",),
        default="non_overlapping",
        help="Research overlap policy.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    run_orb_ohlcv_validation(
        candle_root=args.candle_root,
        manifest_path=args.manifest,
        output_path=args.output,
        holding_minutes=args.holding_minutes,
        friction_bps=args.friction_bps,
        entry_model=args.entry_model,
        overlap_policy=args.overlap_policy,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
