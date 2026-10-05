#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.option_candle_backtest_v1 import (
    CandleBacktestConfig,
    run_option_candle_backtest,
)


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.casefold() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.casefold() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported_table_format:{path}")


def _write(path: Path, payload: object) -> str:
    content = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen slippage sensitivity for option candle research")
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--option-bars", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--slippage-grid-bps", default="0,25,50,100")
    parser.add_argument("--minimum-trades", type=int, default=30)
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--fixed-cost-per-order", type=float, default=20.0)
    parser.add_argument("--entry-cost-bps", type=float, default=0.0)
    parser.add_argument("--exit-cost-bps", type=float, default=0.0)
    parser.add_argument("--stop-pct", type=float, default=0.20)
    parser.add_argument("--target-rr", type=float, default=1.50)
    parser.add_argument("--max-hold-minutes", type=int, default=30)
    parser.add_argument("--require-session-catalog", action="store_true")
    args = parser.parse_args()

    output = args.output_dir.expanduser().resolve(strict=False)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output_directory_not_empty:{output}")
    output.mkdir(parents=True, exist_ok=True)

    grid = tuple(sorted({float(value.strip()) for value in args.slippage_grid_bps.split(",") if value.strip()}))
    if not grid:
        raise ValueError("empty_slippage_grid")

    signals = _read(args.signals)
    catalog = _read(args.catalog)
    bars = _read(args.option_bars)
    scenarios: list[dict[str, object]] = []
    for slippage_bps in grid:
        config = CandleBacktestConfig(
            quantity=args.quantity,
            stop_pct=args.stop_pct,
            target_rr=args.target_rr,
            max_hold_minutes=args.max_hold_minutes,
            entry_slippage_bps=slippage_bps,
            exit_slippage_bps=slippage_bps,
            fixed_cost_per_order=args.fixed_cost_per_order,
            entry_cost_bps=args.entry_cost_bps,
            exit_cost_bps=args.exit_cost_bps,
            require_session_catalog=args.require_session_catalog,
        )
        result = run_option_candle_backtest(
            signals=signals,
            contract_catalog=catalog,
            option_bars=bars,
            config=config,
        )
        scenarios.append(
            {
                "slippage_bps_per_side": slippage_bps,
                "trades": result.summary["trades"],
                "win_rate": result.summary["win_rate"],
                "profit_factor": result.summary["profit_factor"],
                "net_pnl": result.summary["net_pnl"],
                "max_drawdown": result.summary["max_drawdown"],
                "total_costs": result.summary["total_costs"],
            }
        )

    stress_rows = [row for row in scenarios if float(row["slippage_bps_per_side"]) >= 50.0]
    enough_trades = bool(stress_rows) and all(int(row["trades"]) >= args.minimum_trades for row in stress_rows)
    positive_after_stress = bool(stress_rows) and all(
        float(row["net_pnl"]) > 0.0
        and row["profit_factor"] is not None
        and float(row["profit_factor"]) > 1.0
        for row in stress_rows
    )
    survived = enough_trades and positive_after_stress
    payload = {
        "schema_version": "option_candle_sensitivity_v1",
        "result_label": (
            "CANDLE_PROXY_ECONOMICS_SURVIVED_COST_STRESS"
            if survived
            else "CANDLE_PROXY_ECONOMICS_DID_NOT_PASS_COST_STRESS"
        ),
        "minimum_trades": args.minimum_trades,
        "scenarios": scenarios,
        "survived_cost_stress": survived,
        "executable_option_pnl_certified": False,
        "allowed_for_live_execution": False,
        "next_gate": "FORWARD_BID_ASK_VALIDATION",
    }
    _write(output / "sensitivity_summary.json", payload)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
