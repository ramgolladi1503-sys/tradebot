from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.option_backtest.review_queue_eval import evaluate_review_queue_snapshot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate review_queue snapshot rows against same-day option bars."
    )
    parser.add_argument(
        "--review-queue-path",
        default="/Users/madhuram/.codex/worktrees/b411/tradebot/.runtime/logs/review_queue.json",
    )
    parser.add_argument(
        "--db-path",
        default=str(
            getattr(
                cfg,
                "OPTION_SYMBOL_BACKTEST_EXPORT_DB_PATH",
                getattr(cfg, "TRADE_DB_PATH", ".runtime/db/DEFAULT.sqlite"),
            )
        ),
    )
    parser.add_argument(
        "--symbol-prefix",
        default=None,
        help="Optional tradingsymbol prefix filter, e.g. NIFTY",
    )
    parser.add_argument("--output", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    payload = evaluate_review_queue_snapshot(
        review_queue_path=Path(args.review_queue_path),
        db_path=Path(args.db_path),
        symbol_prefix=args.symbol_prefix,
    )
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"rows": payload.get("rows"), "summary": payload.get("summary")},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
