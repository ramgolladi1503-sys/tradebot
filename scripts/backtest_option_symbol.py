from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.option_backtest import OptionBacktestConfig, run_option_symbol_backtest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-symbol option backtest runner")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--from", dest="date_from", default=None)
    parser.add_argument("--to", dest="date_to", default=None)
    parser.add_argument(
        "--output-dir", default=getattr(cfg, "OPTION_SYMBOL_BACKTEST_OUTPUT_DIR", "")
    )
    parser.add_argument(
        "--allow-derived-levels",
        action=argparse.BooleanOptionalAction,
        default=getattr(cfg, "OPTION_SYMBOL_BACKTEST_ALLOW_DERIVED_LEVELS", True),
    )
    parser.add_argument(
        "--require-bid-ask",
        action=argparse.BooleanOptionalAction,
        default=getattr(cfg, "OPTION_SYMBOL_BACKTEST_REQUIRE_BID_ASK", True),
    )
    parser.add_argument(
        "--quantity",
        type=int,
        default=int(getattr(cfg, "OPTION_SYMBOL_BACKTEST_DEFAULT_QTY", 1)),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not bool(getattr(cfg, "OPTION_SYMBOL_BACKTEST_ENABLE", True)):
        print(
            json.dumps(
                {"ok": False, "reason": "OPTION_SYMBOL_BACKTEST_ENABLE=false"},
                sort_keys=True,
            )
        )
        return 1
    output_dir = Path(args.output_dir) if str(args.output_dir).strip() else None
    run_cfg = OptionBacktestConfig(
        symbol=str(args.symbol),
        data_path=Path(args.data),
        date_from=args.date_from,
        date_to=args.date_to,
        timezone=str(getattr(cfg, "OPTION_SYMBOL_BACKTEST_TIMEZONE", "Asia/Kolkata")),
        output_dir=output_dir,
        require_bid_ask=bool(args.require_bid_ask),
        allow_derived_levels=bool(args.allow_derived_levels),
        derived_stop_pct=float(
            getattr(cfg, "OPTION_SYMBOL_BACKTEST_DERIVED_STOP_PCT", 0.12)
        ),
        derived_target_rr=float(
            getattr(cfg, "OPTION_SYMBOL_BACKTEST_DERIVED_TARGET_RR", 1.5)
        ),
        max_hold_minutes=int(
            getattr(cfg, "OPTION_SYMBOL_BACKTEST_MAX_HOLD_MINUTES", 30)
        ),
        quantity=int(args.quantity),
        fill_model_run_id=str(
            getattr(cfg, "OPTION_SYMBOL_BACKTEST_FILL_RUN_ID", "option_backtest")
        ),
    )
    result = run_option_symbol_backtest(run_cfg)
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
