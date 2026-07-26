#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from research.option_e2e_recertification_v4.expired_option_replay_v1.archive_source import (
    prepare_option_source,
)
from research.option_e2e_recertification_v4.expired_option_replay_v1.engine import (
    OptionIntent,
    ReplayDataError,
    build_contract_inventory,
    chronological_partitions,
    metrics,
    replay_intent,
    semantic_hash,
)


def _read_intents(path: Path) -> list[OptionIntent]:
    frame = pd.read_csv(path)
    required = {
        "strategy_id",
        "underlying",
        "signal_timestamp",
        "direction",
        "signal_time_underlying_price",
        "intended_option_type",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise ReplayDataError(f"intent_columns_missing:{','.join(sorted(missing))}")
    out: list[OptionIntent] = []
    for row in frame.to_dict("records"):
        signal = pd.Timestamp(row["signal_timestamp"])
        earliest_raw = row.get("earliest_entry_timestamp")
        earliest = (
            pd.Timestamp(earliest_raw)
            if earliest_raw and not pd.isna(earliest_raw)
            else signal + pd.Timedelta(minutes=1)
        )
        out.append(
            OptionIntent(
                strategy_id=str(row["strategy_id"]),
                underlying=str(row["underlying"]),
                signal_timestamp=signal.to_pydatetime(),
                earliest_entry_timestamp=earliest.to_pydatetime(),
                direction=str(row["direction"]),
                option_type=str(row["intended_option_type"]),
                underlying_price=float(row["signal_time_underlying_price"]),
                expiry_rule=str(row.get("intended_expiry_rule") or "nearest_non_expired"),
                strike_rule="ATM",
                strike_offset_steps=int(row.get("strike_offset_steps") or 0),
                signal_identity_hash=str(row.get("signal_identity_hash") or ""),
            )
        )
    return sorted(
        out,
        key=lambda item: (
            item.signal_timestamp,
            item.strategy_id,
            item.signal_identity_hash,
        ),
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> dict[str, Any]:
    prepared = prepare_option_source(Path(args.option_source))
    try:
        option_root = prepared.root
        output_root = Path(args.output_root).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        intents = _read_intents(Path(args.intents_csv))
        inventory = build_contract_inventory(option_root)
        partitions = chronological_partitions(intents)
        partition_by_date = {
            day: name for name, dates in partitions.items() for day in dates
        }
        trades = []
        blockers: list[dict[str, Any]] = []
        for intent in intents:
            partition = partition_by_date[intent.signal_timestamp.date()]
            if partition == "holdout" and not args.authorize_holdout:
                continue
            try:
                trades.append(
                    replay_intent(
                        intent,
                        option_root,
                        inventory,
                        partition=partition,
                        max_hold_minutes=args.max_hold_minutes,
                        stop_loss_pct=args.stop_loss_pct,
                        target_pct=args.target_pct,
                        friction_bps_per_side=args.friction_bps_per_side,
                    )
                )
            except ReplayDataError as exc:
                blockers.append(
                    {
                        "strategy_id": intent.strategy_id,
                        "signal_timestamp": str(intent.signal_timestamp),
                        "signal_identity_hash": intent.signal_identity_hash,
                        "partition": partition,
                        "exact_reason": str(exc),
                    }
                )
        trade_rows = [trade.to_dict() for trade in trades]
        _write_csv(output_root / "option_trade_ledger.csv", trade_rows)
        _write_csv(output_root / "option_replay_blockers.csv", blockers)
        inventory_rows = [
            {
                "underlying": item.underlying,
                "expiry": item.expiry.isoformat(),
                "option_type": item.option_type,
                "strike": item.strike,
                "instrument_key": item.instrument_key,
                "lot_size": item.lot_size,
                "raw_candle_path": item.raw_candle_path,
            }
            for item in inventory
        ]
        _write_csv(
            output_root / "authority_backed_contract_inventory.csv", inventory_rows
        )
        grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for trade in trades:
            grouped[(trade.strategy_id, trade.partition)].append(trade)
        metric_rows = []
        for (strategy_id, partition), rows in sorted(grouped.items()):
            metric_rows.append(
                {
                    "strategy_id": strategy_id,
                    "partition": partition,
                    **metrics(rows),
                }
            )
        _write_csv(output_root / "strategy_option_metrics.csv", metric_rows)
        expiry_count = len({item.expiry for item in inventory})
        manifest = {
            "schema_version": "expired_option_contract_replay_v1",
            "authority": "UPSTOX_EXPIRED_OPTION_1M_RAW_RESPONSE",
            "normalized_file_presence_is_not_authority": True,
            "option_source": str(prepared.source_path),
            "option_source_kind": prepared.source_kind,
            "option_source_sha256": prepared.source_sha256,
            "source_was_extracted": prepared.extracted,
            "intent_count": len(intents),
            "authority_backed_contract_count": len(inventory),
            "authority_backed_expiry_count": expiry_count,
            "trade_count": len(trades),
            "blocker_count": len(blockers),
            "partition_dates": {
                name: sorted(day.isoformat() for day in dates)
                for name, dates in partitions.items()
            },
            "holdout_authorized": bool(args.authorize_holdout),
            "holdout_outcomes_read": bool(args.authorize_holdout),
            "evaluation_overlay": {
                "max_hold_minutes": args.max_hold_minutes,
                "stop_loss_pct": args.stop_loss_pct,
                "target_pct": args.target_pct,
                "friction_bps_per_side": args.friction_bps_per_side,
            },
            "verdict": (
                "INSUFFICIENT_REAL_OPTION_HISTORY"
                if expiry_count < 3
                else "OPTION_REPLAY_COMPLETED"
            ),
        }
        manifest["semantic_hash"] = semantic_hash(manifest)
        (output_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return manifest
    finally:
        prepared.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay canonical TradeBot signal intents against real expired option "
            "minute candles from a dataset directory or ZIP archive."
        )
    )
    parser.add_argument(
        "--option-source",
        required=True,
        help="Dataset directory or ZIP containing raw/responses and normalized folders",
    )
    parser.add_argument(
        "--intents-csv",
        required=True,
        help="Canonical option-intent CSV from the directional campaign",
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--max-hold-minutes", type=int, default=30)
    parser.add_argument("--stop-loss-pct", type=float, default=0.25)
    parser.add_argument("--target-pct", type=float, default=0.375)
    parser.add_argument("--friction-bps-per-side", type=float, default=5.0)
    parser.add_argument(
        "--authorize-holdout",
        action="store_true",
        help="Explicitly authorize holdout outcome reads",
    )
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
