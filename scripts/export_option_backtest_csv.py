from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
import sys

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.option_backtest.exporter import export_option_backtest_csv, resolve_instrument_token


_DEFAULT_INSTRUMENTS_PATH = Path(getattr(cfg, "DATA_DIR", Path.cwd() / "data")) / "kite_instruments.json"
_DEFAULT_BACKTEST_OUTPUT_DIR = Path(getattr(cfg, "RUNTIME_DIR", Path.cwd() / ".runtime")) / "backtest"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export one option contract from live SQLite data into a backtest CSV.")
    parser.add_argument("--tradingsymbol", default=None, help="Exact option tradingsymbol, e.g. NIFTY2650524200CE")
    parser.add_argument("--instrument-token", type=int, default=None, help="Exact option instrument token.")
    parser.add_argument("--from", dest="date_from", default=None, help="Start date in YYYY-MM-DD, Asia/Kolkata.")
    parser.add_argument("--to", dest="date_to", default=None, help="End date in YYYY-MM-DD, Asia/Kolkata.")
    parser.add_argument("--db-path", default=str(getattr(cfg, "OPTION_SYMBOL_BACKTEST_EXPORT_DB_PATH", getattr(cfg, "TRADE_DB_PATH", Path.cwd() / ".runtime" / "db" / "DEFAULT.sqlite"))))
    parser.add_argument("--output", default=None, help="Output CSV path.")
    parser.add_argument("--option-chain-path", default=str(getattr(cfg, "OPTION_SYMBOL_BACKTEST_EXPORT_CHAIN_PATH", Path.cwd() / ".runtime" / "option_chain_latest.json")))
    parser.add_argument("--instruments-path", default=str(getattr(cfg, "OPTION_SYMBOL_BACKTEST_EXPORT_INSTRUMENTS_PATH", _DEFAULT_INSTRUMENTS_PATH)))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not bool(getattr(cfg, "OPTION_SYMBOL_BACKTEST_ENABLE", True)):
        print(json.dumps({"ok": False, "reason": "OPTION_SYMBOL_BACKTEST_ENABLE=false"}, sort_keys=True))
        return 1
    tradingsymbol = str(args.tradingsymbol or "").strip().upper()
    instrument_token = args.instrument_token
    if instrument_token is None:
        if not tradingsymbol:
            raise SystemExit("Either --tradingsymbol or --instrument-token is required.")
        resolved = resolve_instrument_token(
            tradingsymbol=tradingsymbol,
            option_chain_path=Path(args.option_chain_path),
            instruments_path=Path(args.instruments_path),
        )
        instrument_token = int(resolved["instrument_token"])
        tradingsymbol = str(resolved["tradingsymbol"])
    elif not tradingsymbol:
        tradingsymbol = f"TOKEN_{int(instrument_token)}"

    output_path = Path(
        args.output
        or (
            Path(str(getattr(cfg, "OPTION_SYMBOL_BACKTEST_EXPORT_OUTPUT_DIR", _DEFAULT_BACKTEST_OUTPUT_DIR)))
            / f"{tradingsymbol}_1min.csv"
        )
    )
    payload = export_option_backtest_csv(
        db_path=Path(args.db_path),
        output_path=output_path,
        tradingsymbol=tradingsymbol,
        instrument_token=int(instrument_token),
        date_from=args.date_from,
        date_to=args.date_to,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
