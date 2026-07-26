#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from research.option_e2e_recertification_v4.expired_option_replay_v1.archive_source import (
    prepare_option_source,
)
from research.option_e2e_recertification_v4.expired_option_replay_v1.engine import (
    OptionIntent,
    ReplayDataError,
    ReplayTrade,
    build_contract_inventory,
    chronological_partitions,
    metrics,
    profit_factor,
    replay_intent,
    semantic_hash,
)

FRICTION_SENSITIVITY_BPS = (0.0, 5.0, 10.0, 25.0)


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
        partition_raw = row.get("partition")
        partition = (
            None
            if partition_raw is None or pd.isna(partition_raw)
            else str(partition_raw).strip().lower()
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
                strike_rule=str(row.get("strike_rule") or "ATM"),
                strike_offset_steps=int(row.get("strike_offset_steps") or 0),
                signal_identity_hash=str(row.get("signal_identity_hash") or ""),
                partition=partition,
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


def _write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    fieldnames: Iterable[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(fieldnames or sorted({key for row in rows for key in row}))
    if not fields:
        fields = ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)


def _friction_sensitivity(
    strategy_id: str, partition: str, trades: list[ReplayTrade]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bps in FRICTION_SENSITIVITY_BPS:
        values = [
            trade.gross_pnl
            - (
                (trade.entry_price + trade.exit_price)
                * trade.quantity
                * bps
                / 10000.0
            )
            for trade in trades
        ]
        rows.append(
            {
                "strategy_id": strategy_id,
                "partition": partition,
                "friction_bps_per_side": bps,
                "trades": len(values),
                "profit_factor": profit_factor(values),
                "net_pnl": sum(values),
                "expectancy": sum(values) / len(values) if values else None,
            }
        )
    return rows


def _wfa_rows(
    intents: list[OptionIntent],
    trades: list[ReplayTrade],
    *,
    minimum_partition_trades: int,
) -> list[dict[str, Any]]:
    strategies = sorted({intent.strategy_id for intent in intents})
    grouped: dict[tuple[str, str], list[ReplayTrade]] = defaultdict(list)
    for trade in trades:
        grouped[(trade.strategy_id, trade.partition)].append(trade)
    rows: list[dict[str, Any]] = []
    for strategy_id in strategies:
        development = metrics(grouped[(strategy_id, "development")])
        validation = metrics(grouped[(strategy_id, "validation")])
        if (
            development["trades"] < minimum_partition_trades
            or validation["trades"] < minimum_partition_trades
        ):
            verdict = "INSUFFICIENT_MATCHED_TRADES_FOR_WFA"
        elif (
            (development["profit_factor"] or 0.0) > 1.0
            and (validation["profit_factor"] or 0.0) > 1.0
            and (development["expectancy"] or 0.0) > 0.0
            and (validation["expectancy"] or 0.0) > 0.0
        ):
            verdict = "WFA_VALIDATION_SURVIVOR_HOLDOUT_SEALED"
        else:
            verdict = "NO_WFA_EDGE"
        rows.append(
            {
                "strategy_id": strategy_id,
                "wfa_policy": "frozen_chronological_development_validation_gate_v1",
                "minimum_partition_trades": minimum_partition_trades,
                "development_trades": development["trades"],
                "development_profit_factor": development["profit_factor"],
                "development_expectancy": development["expectancy"],
                "development_maximum_drawdown": development["maximum_drawdown"],
                "validation_trades": validation["trades"],
                "validation_profit_factor": validation["profit_factor"],
                "validation_expectancy": validation["expectancy"],
                "validation_maximum_drawdown": validation["maximum_drawdown"],
                "holdout_profit_factor": "SEALED",
                "holdout_outcomes_read": False,
                "verdict": verdict,
                "allowed_for_live_execution": False,
            }
        )
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    prepared = prepare_option_source(Path(args.option_source))
    try:
        option_root = prepared.root
        output_root = Path(args.output_root).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        intents = _read_intents(Path(args.intents_csv))
        inventory = build_contract_inventory(option_root)
        derived_partitions = chronological_partitions(intents)
        derived_partition_by_date = {
            day: name for name, dates in derived_partitions.items() for day in dates
        }
        partition_authority = (
            "INTENT_LEDGER"
            if intents and all(intent.partition for intent in intents)
            else "DERIVED_60_20_20"
        )

        trades: list[ReplayTrade] = []
        blockers: list[dict[str, Any]] = []
        sealed_holdout_intent_count = 0
        for intent in intents:
            partition = (
                intent.partition
                or derived_partition_by_date[intent.signal_timestamp.date()]
            )
            if partition == "holdout" and not args.authorize_holdout:
                sealed_holdout_intent_count += 1
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
                        "underlying": intent.underlying,
                        "signal_timestamp": str(intent.signal_timestamp),
                        "signal_identity_hash": intent.signal_identity_hash,
                        "partition": partition,
                        "exact_reason": str(exc),
                    }
                )

        _write_csv(
            output_root / "option_trade_ledger.csv",
            [trade.to_dict() for trade in trades],
        )
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
                "first_session_date": (
                    item.first_session_date.isoformat()
                    if item.first_session_date
                    else None
                ),
                "last_session_date": (
                    item.last_session_date.isoformat()
                    if item.last_session_date
                    else None
                ),
                "session_count": len(item.session_dates),
            }
            for item in inventory
        ]
        _write_csv(
            output_root / "authority_backed_contract_inventory.csv",
            inventory_rows,
        )

        grouped: dict[tuple[str, str], list[ReplayTrade]] = defaultdict(list)
        for trade in trades:
            grouped[(trade.strategy_id, trade.partition)].append(trade)
        metric_rows: list[dict[str, Any]] = []
        sensitivity_rows: list[dict[str, Any]] = []
        for (strategy_id, partition), strategy_trades in sorted(grouped.items()):
            metric_rows.append(
                {
                    "strategy_id": strategy_id,
                    "partition": partition,
                    **metrics(strategy_trades),
                }
            )
            sensitivity_rows.extend(
                _friction_sensitivity(strategy_id, partition, strategy_trades)
            )
        _write_csv(output_root / "strategy_option_metrics.csv", metric_rows)
        _write_csv(
            output_root / "strategy_friction_sensitivity.csv",
            sensitivity_rows,
        )

        wfa_rows = _wfa_rows(
            intents,
            trades,
            minimum_partition_trades=args.minimum_partition_trades,
        )
        _write_csv(output_root / "strategy_wfa_summary.csv", wfa_rows)
        survivors = [
            row
            for row in wfa_rows
            if row["verdict"] == "WFA_VALIDATION_SURVIVOR_HOLDOUT_SEALED"
        ]

        expiry_count = len({item.expiry for item in inventory})
        session_dates = {
            session_date
            for item in inventory
            for session_date in item.session_dates
        }
        if not intents:
            verdict = "NO_CANONICAL_OPTION_INTENTS"
        elif not trades:
            verdict = "NO_MATCHED_OPTION_REPLAY_TRADES"
        elif survivors:
            verdict = "PRELIMINARY_VALIDATION_SURVIVOR_HOLDOUT_SEALED"
        else:
            verdict = "NO_VALIDATED_OPTION_EDGE"

        manifest = {
            "schema_version": "expired_option_contract_replay_v1",
            "authority": "UPSTOX_EXPIRED_OPTION_1M_RAW_RESPONSE",
            "normalized_file_presence_is_not_authority": True,
            "same_session_contract_price_authority_required": True,
            "option_source": str(prepared.source_path),
            "option_source_kind": prepared.source_kind,
            "option_source_sha256": prepared.source_sha256,
            "source_was_extracted": prepared.extracted,
            "intent_count": len(intents),
            "partition_authority": partition_authority,
            "authority_backed_contract_count": len(inventory),
            "authority_backed_expiry_count": expiry_count,
            "authority_backed_session_count": len(session_dates),
            "trade_count": len(trades),
            "blocker_count": len(blockers),
            "sealed_holdout_intent_count": sealed_holdout_intent_count,
            "wfa_survivor_count": len(survivors),
            "derived_partition_dates": {
                name: sorted(day.isoformat() for day in dates)
                for name, dates in derived_partitions.items()
            },
            "holdout_authorized": bool(args.authorize_holdout),
            "holdout_outcomes_read": bool(args.authorize_holdout),
            "evaluation_overlay": {
                "max_hold_minutes": args.max_hold_minutes,
                "stop_loss_pct": args.stop_loss_pct,
                "target_pct": args.target_pct,
                "friction_bps_per_side": args.friction_bps_per_side,
                "minimum_partition_trades": args.minimum_partition_trades,
                "ambiguous_stop_target_bar_policy": "STOP_FIRST_CONSERVATIVE",
            },
            "verdict": verdict,
            "allowed_for_live_execution": False,
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
        "--intents-csv", required=True, help="Canonical option-intent CSV"
    )
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--max-hold-minutes", type=int, default=30)
    parser.add_argument("--stop-loss-pct", type=float, default=0.25)
    parser.add_argument("--target-pct", type=float, default=0.375)
    parser.add_argument("--friction-bps-per-side", type=float, default=5.0)
    parser.add_argument("--minimum-partition-trades", type=int, default=30)
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
