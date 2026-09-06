#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.option_candle_backtest_v1 import (
    CandleBacktestConfig,
    run_option_candle_backtest,
)


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported_table_format:{path}")


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"


def _write_json(path: Path, payload: object) -> str:
    content = _canonical_json(payload)
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Research-only option OHLCV backtest")
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--option-bars", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--stop-pct", type=float, default=0.20)
    parser.add_argument("--target-rr", type=float, default=1.50)
    parser.add_argument("--max-hold-minutes", type=int, default=30)
    parser.add_argument("--entry-slippage-bps", type=float, default=50.0)
    parser.add_argument("--exit-slippage-bps", type=float, default=50.0)
    parser.add_argument("--fixed-cost-per-order", type=float, default=20.0)
    parser.add_argument("--entry-cost-bps", type=float, default=0.0)
    parser.add_argument("--exit-cost-bps", type=float, default=0.0)
    parser.add_argument("--max-volume-participation", type=float, default=0.02)
    parser.add_argument("--require-session-catalog", action="store_true")
    args = parser.parse_args()

    output = args.output_dir.expanduser().resolve(strict=False)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output_directory_not_empty:{output}")
    output.mkdir(parents=True, exist_ok=True)

    config = CandleBacktestConfig(
        quantity=args.quantity,
        stop_pct=args.stop_pct,
        target_rr=args.target_rr,
        max_hold_minutes=args.max_hold_minutes,
        entry_slippage_bps=args.entry_slippage_bps,
        exit_slippage_bps=args.exit_slippage_bps,
        fixed_cost_per_order=args.fixed_cost_per_order,
        entry_cost_bps=args.entry_cost_bps,
        exit_cost_bps=args.exit_cost_bps,
        max_volume_participation=args.max_volume_participation,
        require_session_catalog=args.require_session_catalog,
    )
    result = run_option_candle_backtest(
        signals=_read_table(args.signals),
        contract_catalog=_read_table(args.catalog),
        option_bars=_read_table(args.option_bars),
        config=config,
    )

    artifact_hashes = {
        "summary.json": _write_json(output / "summary.json", result.summary),
        "trades.json": _write_json(output / "trades.json", [trade.to_dict() for trade in result.trades]),
        "rejections.json": _write_json(output / "rejections.json", result.rejections),
        "contract_selections.json": _write_json(output / "contract_selections.json", result.selections),
        "config.json": _write_json(output / "config.json", asdict(config)),
    }
    manifest = {
        "schema_version": "option_candle_backtest_manifest_v1",
        "artifacts": artifact_hashes,
        "result_label": result.summary["result_label"],
        "executable_option_pnl_certified": False,
        "allowed_for_live_execution": False,
        "broker_api_called": False,
    }
    _write_json(output / "manifest.json", manifest)
    print(_canonical_json(result.summary), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
