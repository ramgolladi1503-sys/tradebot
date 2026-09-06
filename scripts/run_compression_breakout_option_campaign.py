#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.compression_breakout_option_campaign_v1 import (
    CompressionCampaignConfig,
    CompressionLedgerConfig,
    run_compression_campaign,
)


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported_table_format:{path}")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(payload: object) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ) + "\n"


def _write_json(path: Path, payload: object) -> str:
    content = _canonical(payload)
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return digest


def _write_csv(path: Path, frame: pd.DataFrame) -> str:
    content = frame.to_csv(index=False, lineterminator="\n")
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Causal Compression Breakout to CE/PE candle campaign"
    )
    parser.add_argument("--underlying-bars", type=Path, required=True)
    parser.add_argument("--contract-catalog", type=Path)
    parser.add_argument("--option-bars", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--partition",
        choices=("development", "validation", "all_non_holdout", "smoke"),
        default="development",
    )
    parser.add_argument(
        "--timestamp-semantics", choices=("START", "END"), default="START"
    )
    parser.add_argument("--bar-interval-minutes", type=int, default=1)
    parser.add_argument("--disallow-vwap-proxy", action="store_true")
    parser.add_argument("--slippage-grid-bps", default="0,25,50,100")
    parser.add_argument("--minimum-trades", type=int, default=30)
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--stop-pct", type=float, default=0.20)
    parser.add_argument("--target-rr", type=float, default=1.50)
    parser.add_argument("--max-hold-minutes", type=int, default=30)
    parser.add_argument("--fixed-cost-per-order", type=float, default=20.0)
    parser.add_argument("--entry-cost-bps", type=float, default=0.0)
    parser.add_argument("--exit-cost-bps", type=float, default=0.0)
    parser.add_argument("--max-volume-participation", type=float, default=0.02)
    args = parser.parse_args()

    if (args.contract_catalog is None) != (args.option_bars is None):
        raise ValueError("contract_catalog_and_option_bars_must_be_supplied_together")

    output = args.output_dir.expanduser().resolve(strict=False)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output_directory_not_empty:{output}")
    output.mkdir(parents=True, exist_ok=True)

    underlying_path = args.underlying_bars.expanduser().resolve(strict=True)
    source_hash = _file_hash(underlying_path)
    ledger_config = CompressionLedgerConfig(
        timestamp_semantics=args.timestamp_semantics,
        bar_interval_minutes=args.bar_interval_minutes,
        allow_typical_price_vwap_proxy=not args.disallow_vwap_proxy,
    )
    campaign_config = CompressionCampaignConfig(
        partition=args.partition,
        slippage_grid_bps=tuple(
            float(value.strip())
            for value in args.slippage_grid_bps.split(",")
            if value.strip()
        ),
        minimum_trades=args.minimum_trades,
        quantity=args.quantity,
        stop_pct=args.stop_pct,
        target_rr=args.target_rr,
        max_hold_minutes=args.max_hold_minutes,
        fixed_cost_per_order=args.fixed_cost_per_order,
        entry_cost_bps=args.entry_cost_bps,
        exit_cost_bps=args.exit_cost_bps,
        max_volume_participation=args.max_volume_participation,
        require_session_catalog=True,
        ledger_config=ledger_config,
    )

    catalog = (
        _read_table(args.contract_catalog.expanduser().resolve(strict=True))
        if args.contract_catalog is not None
        else None
    )
    option_bars = (
        _read_table(args.option_bars.expanduser().resolve(strict=True))
        if args.option_bars is not None
        else None
    )
    result = run_compression_campaign(
        underlying_bars=_read_table(underlying_path),
        contract_catalog=catalog,
        option_bars=option_bars,
        config=campaign_config,
        source_dataset_hash=source_hash,
    )

    hashes: dict[str, str] = {
        "signal_ledger.csv": _write_csv(output / "signal_ledger.csv", result.ledger.signals),
        "signal_rejections.csv": _write_csv(
            output / "signal_rejections.csv", result.ledger.rejections
        ),
        "split_manifest.json": _write_json(
            output / "split_manifest.json", result.ledger.split_manifest
        ),
        "signal_ledger_summary.json": _write_json(
            output / "signal_ledger_summary.json", result.ledger.summary
        ),
        "campaign_summary.json": _write_json(
            output / "campaign_summary.json", result.summary
        ),
        "sensitivity.json": _write_json(output / "sensitivity.json", result.sensitivity),
        "controls.json": _write_json(output / "controls.json", result.controls),
        "campaign_config.json": _write_json(
            output / "campaign_config.json",
            {**asdict(campaign_config), "ledger_config": asdict(ledger_config)},
        ),
    }
    if result.base_result is not None:
        hashes["base_summary.json"] = _write_json(
            output / "base_summary.json", result.base_result.summary
        )
        hashes["base_trades.json"] = _write_json(
            output / "base_trades.json",
            [trade.to_dict() for trade in result.base_result.trades],
        )
        hashes["base_rejections.json"] = _write_json(
            output / "base_rejections.json", result.base_result.rejections
        )
        hashes["contract_selections.json"] = _write_json(
            output / "contract_selections.json", result.base_result.selections
        )

    manifest = {
        "schema_version": "compression_breakout_option_campaign_manifest_v1",
        "strategy_id": "compression_breakout_v1",
        "source_underlying_sha256": source_hash,
        "artifacts": hashes,
        "campaign_status": result.summary["campaign_status"],
        "research_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "executable_option_pnl_certified": False,
    }
    _write_json(output / "manifest.json", manifest)
    print(json.dumps(result.summary, sort_keys=True, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
