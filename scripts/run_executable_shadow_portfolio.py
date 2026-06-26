from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.analytics.shadow_portfolio import build_executable_shadow_portfolio_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulate executable review-queue rows as offline fills."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Exchange date in YYYY-MM-DD. Defaults to today in IST.",
    )
    parser.add_argument(
        "--review-queue-path",
        action="append",
        dest="review_queue_paths",
        default=None,
        help="Optional review_queue.json override. May be supplied multiple times.",
    )
    parser.add_argument(
        "--lookahead-min", type=int, default=None, help="Exit horizon in minutes."
    )
    parser.add_argument("--interval", default=None, help="Candle interval.")
    parser.add_argument(
        "--entry-mode",
        choices=["MARK", "SIDE_QUOTE"],
        default=None,
        help="Entry reference mode.",
    )
    parser.add_argument(
        "--slippage-model",
        choices=["bps", "spread"],
        default=None,
        help="Slippage model.",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=None,
        help="Slippage in bps for the bps model.",
    )
    parser.add_argument(
        "--spread-slippage-mult",
        type=float,
        default=None,
        help="Spread multiplier for the spread model.",
    )
    parser.add_argument(
        "--starting-equity",
        type=float,
        default=None,
        help="Initial equity for the equity curve.",
    )
    parser.add_argument(
        "--output", default=None, help="Optional output JSON path override."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not bool(getattr(cfg, "EXECUTABLE_SHADOW_PORTFOLIO_ENABLE", True)):
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "EXECUTABLE_SHADOW_PORTFOLIO_ENABLE=false",
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 1

    output_path = Path(args.output) if args.output else None
    review_queue_paths = (
        [Path(item) for item in args.review_queue_paths]
        if args.review_queue_paths
        else None
    )
    payload = build_executable_shadow_portfolio_report(
        args.date or None,
        review_queue_paths=review_queue_paths,
        lookahead_minutes=args.lookahead_min,
        interval=args.interval,
        entry_mode=args.entry_mode,
        slippage_model=args.slippage_model,
        slippage_bps=args.slippage_bps,
        spread_slippage_mult=args.spread_slippage_mult,
        starting_equity=args.starting_equity,
        output_path=output_path,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "date": payload.get("date"),
                "scope": payload.get("scope"),
                "summary": payload.get("summary"),
                "counts": payload.get("counts"),
                "skip_reasons": payload.get("skip_reasons"),
                "output_path": payload.get("output_path"),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
