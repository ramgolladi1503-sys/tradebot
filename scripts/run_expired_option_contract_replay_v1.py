#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from research.option_e2e_recertification_v4.expired_option_replay_v1.archive_source import (
    prepare_option_source,
)
from research.option_e2e_recertification_v4.expired_option_replay_v1.engine import (
    DEFAULT_MAX_EXPIRY_GAP_DAYS,
    DEFAULT_MAX_SIGNAL_TO_ENTRY_SECONDS,
    OptionIntent,
    ReplayDataError,
    ReplayTrade,
    build_contract_inventory,
    build_contract_universe,
    chronological_partitions,
    exact_atm_strike,
    metrics,
    profit_factor,
    replay_intent,
    resolve_expiry,
    semantic_hash,
    strike_step,
)

FRICTION_SENSITIVITY_BPS = (0.0, 5.0, 15.0, 25.0)
NORMALIZATIONS = ("one_lot_rupee", "per_option_unit", "net_return_pct")


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


def _blocker_class(reason: str) -> str:
    if reason.startswith("nearest_expiry_universe_gap_exceeds_"):
        return "EXPIRY_UNIVERSE_COVERAGE_MISSING"
    if reason.startswith("nearest_expiry_metadata_unavailable"):
        return "EXPIRY_METADATA_MISSING"
    if reason.startswith("nearest_expiry_has_no_same_session_price_authority"):
        return "SAME_SESSION_OPTION_AUTHORITY_MISSING"
    if reason.startswith("exact_atm_contract_unavailable"):
        return "EXACT_ATM_CONTRACT_UNAVAILABLE"
    if reason.startswith("signal_to_entry_lag_exceeds_"):
        return "ENTRY_LAG_EXCEEDED"
    if reason in {
        "no_legal_same_session_entry_bar",
        "selected_contract_has_no_same_session_candles",
        "empty_same_session_exit_window",
    }:
        return "ENTRY_OR_EXIT_TIMING_UNAVAILABLE"
    return "OTHER_REPLAY_BLOCKER"


def _metric_values(trades: Sequence[ReplayTrade], normalization: str, bps: float) -> list[float]:
    values: list[float] = []
    for trade in trades:
        unit_net = trade.unit_gross_pnl - (
            (trade.entry_price + trade.exit_price) * bps / 10000.0
        )
        if normalization == "one_lot_rupee":
            values.append(unit_net * trade.quantity)
        elif normalization == "per_option_unit":
            values.append(unit_net)
        elif normalization == "net_return_pct":
            values.append(unit_net / trade.entry_price * 100.0)
        else:
            raise ReplayDataError(f"unsupported_metric_normalization:{normalization}")
    return values


def _friction_sensitivity(
    strategy_id: str, partition: str, trades: list[ReplayTrade]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bps in FRICTION_SENSITIVITY_BPS:
        for normalization in NORMALIZATIONS:
            values = _metric_values(trades, normalization, bps)
            rows.append(
                {
                    "strategy_id": strategy_id,
                    "partition": partition,
                    "evidence_lane": "PRICE_STRUCTURE_CANDIDATE_OVERLAY",
                    "overlay_name": "COMMON_OPTION_OVERLAY_V1",
                    "friction_bps_per_side": bps,
                    "normalization": normalization,
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
        dev_trades = grouped[(strategy_id, "development")]
        val_trades = grouped[(strategy_id, "validation")]
        by_norm: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
            normalization: (
                metrics(dev_trades, normalization=normalization),
                metrics(val_trades, normalization=normalization),
            )
            for normalization in NORMALIZATIONS
        }
        if (
            len(dev_trades) < minimum_partition_trades
            or len(val_trades) < minimum_partition_trades
        ):
            verdict = "INSUFFICIENT_OPTION_TRANSLATION_SAMPLE"
        else:
            passed = all(
                (development["profit_factor"] or 0.0) > 1.0
                and (validation["profit_factor"] or 0.0) > 1.0
                and (development["expectancy"] or 0.0) > 0.0
                and (validation["expectancy"] or 0.0) > 0.0
                for development, validation in by_norm.values()
            )
            verdict = (
                "OPTION_TRANSLATION_VALIDATION_SURVIVOR_HOLDOUT_SEALED"
                if passed
                else "NO_VALIDATED_OPTION_TRANSLATION_EDGE"
            )
        row: dict[str, Any] = {
            "strategy_id": strategy_id,
            "evidence_lane": "PRICE_STRUCTURE_CANDIDATE_OVERLAY",
            "overlay_name": "COMMON_OPTION_OVERLAY_V1",
            "wfa_policy": "frozen_chronological_development_validation_gate_v2",
            "minimum_partition_trades": minimum_partition_trades,
            "development_trades": len(dev_trades),
            "validation_trades": len(val_trades),
            "holdout_profit_factor": "SEALED",
            "holdout_outcomes_read": False,
            "verdict": verdict,
            "allowed_for_live_execution": False,
        }
        for normalization, (development, validation) in by_norm.items():
            prefix = {
                "one_lot_rupee": "one_lot",
                "per_option_unit": "per_unit",
                "net_return_pct": "return_pct",
            }[normalization]
            row[f"development_{prefix}_profit_factor"] = development["profit_factor"]
            row[f"development_{prefix}_expectancy"] = development["expectancy"]
            row[f"validation_{prefix}_profit_factor"] = validation["profit_factor"]
            row[f"validation_{prefix}_expectancy"] = validation["expectancy"]
        rows.append(row)
    return rows


def _coverage_rows(
    intents: Sequence[OptionIntent],
    trades: Sequence[ReplayTrade],
    blockers: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    matched = {trade.signal_identity_hash for trade in trades}
    blocker_by_hash = {
        str(row["signal_identity_hash"]): str(row["blocker_class"])
        for row in blockers
    }
    grouped: dict[tuple[str, str, str], list[OptionIntent]] = defaultdict(list)
    for intent in intents:
        grouped[(intent.strategy_id, str(intent.partition), intent.direction)].append(intent)
    rows: list[dict[str, Any]] = []
    for (strategy_id, partition, direction), group in sorted(grouped.items()):
        reason_counts = Counter(
            blocker_by_hash.get(intent.signal_identity_hash, "MATCHED")
            if intent.signal_identity_hash not in matched
            else "MATCHED"
            for intent in group
        )
        matched_count = reason_counts.pop("MATCHED", 0)
        rows.append(
            {
                "strategy_id": strategy_id,
                "partition": partition,
                "direction": direction,
                "intent_count": len(group),
                "matched_trade_count": matched_count,
                "unmatched_count": len(group) - matched_count,
                "match_rate": matched_count / len(group) if group else None,
                "blocker_counts_json": json.dumps(dict(sorted(reason_counts.items())), sort_keys=True),
            }
        )
    return rows


def _offset_sensitivity(
    intents: Sequence[OptionIntent],
    *,
    option_root: Path,
    inventory: Sequence[Any],
    universe: Sequence[Any],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in (-1, 1):
        grouped: dict[tuple[str, str], list[ReplayTrade]] = defaultdict(list)
        blockers: Counter[str] = Counter()
        for intent in intents:
            partition = str(intent.partition)
            if partition == "holdout" and not args.authorize_holdout:
                continue
            shifted = replace(intent, strike_offset_steps=offset)
            try:
                trade = replay_intent(
                    shifted,
                    option_root,
                    inventory,
                    contract_universe=universe,
                    partition=partition,
                    max_hold_minutes=args.max_hold_minutes,
                    stop_loss_pct=args.stop_loss_pct,
                    target_pct=args.target_pct,
                    friction_bps_per_side=args.friction_bps_per_side,
                    max_signal_to_entry_seconds=args.max_signal_to_entry_seconds,
                    max_expiry_gap_days=args.max_expiry_gap_days,
                )
                grouped[(trade.strategy_id, trade.partition)].append(trade)
            except ReplayDataError as exc:
                blockers[_blocker_class(str(exc))] += 1
        for strategy_id in sorted({intent.strategy_id for intent in intents}):
            for partition in ("development", "validation"):
                strategy_trades = grouped[(strategy_id, partition)]
                result = metrics(strategy_trades, normalization="per_option_unit")
                rows.append(
                    {
                        "strategy_id": strategy_id,
                        "partition": partition,
                        "strike_offset_steps": offset,
                        "strike_distance_points": offset * 50,
                        "lane": "ATM_PLUS_MINUS_50_SENSITIVITY_ONLY",
                        "trades": result["trades"],
                        "per_unit_profit_factor": result["profit_factor"],
                        "per_unit_expectancy": result["expectancy"],
                        "global_blocker_counts_json": json.dumps(dict(sorted(blockers.items())), sort_keys=True),
                        "allowed_for_strategy_verdict": False,
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
        universe = build_contract_universe(option_root)
        inventory = tuple(item for item in universe if item.has_price_authority)
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
                        contract_universe=universe,
                        partition=partition,
                        max_hold_minutes=args.max_hold_minutes,
                        stop_loss_pct=args.stop_loss_pct,
                        target_pct=args.target_pct,
                        friction_bps_per_side=args.friction_bps_per_side,
                        max_signal_to_entry_seconds=args.max_signal_to_entry_seconds,
                        max_expiry_gap_days=args.max_expiry_gap_days,
                    )
                )
            except ReplayDataError as exc:
                reason = str(exc)
                try:
                    expected_expiry = resolve_expiry(
                        intent,
                        universe,
                        max_expiry_gap_days=args.max_expiry_gap_days,
                    ).isoformat()
                except ReplayDataError:
                    expected_expiry = None
                blockers.append(
                    {
                        "strategy_id": intent.strategy_id,
                        "underlying": intent.underlying,
                        "signal_timestamp": str(intent.signal_timestamp),
                        "signal_identity_hash": intent.signal_identity_hash,
                        "partition": partition,
                        "direction": intent.direction,
                        "underlying_price": intent.underlying_price,
                        "expected_expiry": expected_expiry,
                        "expected_atm_strike": exact_atm_strike(
                            intent.underlying, intent.underlying_price
                        ),
                        "blocker_class": _blocker_class(reason),
                        "exact_reason": reason,
                    }
                )

        if len(trades) + len(blockers) + sealed_holdout_intent_count != len(intents):
            raise ReplayDataError("intent_trade_blocker_reconciliation_failed")

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
                "raw_contract_path": item.raw_contract_path,
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
        for strategy_id in sorted({intent.strategy_id for intent in intents}):
            for partition in ("development", "validation"):
                strategy_trades = grouped[(strategy_id, partition)]
                for normalization in NORMALIZATIONS:
                    metric_rows.append(
                        {
                            "strategy_id": strategy_id,
                            "partition": partition,
                            "evidence_lane": "PRICE_STRUCTURE_CANDIDATE_OVERLAY",
                            "overlay_name": "COMMON_OPTION_OVERLAY_V1",
                            **metrics(strategy_trades, normalization=normalization),
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
            if row["verdict"]
            == "OPTION_TRANSLATION_VALIDATION_SURVIVOR_HOLDOUT_SEALED"
        ]

        coverage_rows = _coverage_rows(intents, trades, blockers)
        _write_csv(output_root / "matched_unmatched_coverage.csv", coverage_rows)
        blocker_summary = [
            {"blocker_class": reason, "count": count}
            for reason, count in sorted(Counter(row["blocker_class"] for row in blockers).items())
        ]
        _write_csv(output_root / "blocker_summary.csv", blocker_summary)
        offset_rows = _offset_sensitivity(
            intents,
            option_root=option_root,
            inventory=inventory,
            universe=universe,
            args=args,
        )
        _write_csv(output_root / "atm_plus_minus_50_sensitivity.csv", offset_rows)

        expiry_count = len({item.expiry for item in inventory})
        universe_expiry_count = len({item.expiry for item in universe})
        session_dates = {
            session_date
            for item in inventory
            for session_date in item.session_dates
        }
        eligible_wfa_rows = [
            row
            for row in wfa_rows
            if row["verdict"] != "INSUFFICIENT_OPTION_TRANSLATION_SAMPLE"
        ]
        if not intents:
            verdict = "NO_CANONICAL_OPTION_INTENTS"
        elif not trades:
            verdict = "INSUFFICIENT_OPTION_TRANSLATION_SAMPLE"
        elif survivors:
            verdict = "OPTION_TRANSLATION_EDGE_VALIDATED_HOLDOUT_SEALED"
        elif eligible_wfa_rows:
            verdict = "NO_VALIDATED_OPTION_TRANSLATION_EDGE"
        else:
            verdict = "INSUFFICIENT_OPTION_TRANSLATION_SAMPLE"

        manifest = {
            "schema_version": "expired_option_contract_replay_v2_logic_integrity",
            "authority": "UPSTOX_EXPIRED_OPTION_1M_RAW_RESPONSE",
            "evidence_lane": "PRICE_STRUCTURE_CANDIDATE_OVERLAY",
            "executable_strategy_evidence": "UNAVAILABLE_WITH_HISTORICAL_PHASE2_TRUTH",
            "overlay_name": "COMMON_OPTION_OVERLAY_V1",
            "native_strategy_profit_factor_claimed": False,
            "normalized_file_presence_is_not_authority": True,
            "true_expiry_resolution_policy": "NEAREST_NON_EXPIRED_FROM_SUPPLIED_CONTRACT_METADATA_WITH_MAX_7_DAY_GAP_THEN_REQUIRE_SAME_SESSION_CANDLES",
            "same_session_contract_price_authority_required": True,
            "exact_atm_contract_required": True,
            "atm_rounding_policy": "NIFTY_50_POINT_ROUND_HALF_UP",
            "distant_strike_substitution_allowed": False,
            "option_source": str(prepared.source_path),
            "option_source_kind": prepared.source_kind,
            "option_source_sha256": prepared.source_sha256,
            "source_was_extracted": prepared.extracted,
            "intent_count": len(intents),
            "partition_authority": partition_authority,
            "contract_metadata_count": len(universe),
            "contract_metadata_expiry_count": universe_expiry_count,
            "authority_backed_contract_count": len(inventory),
            "authority_backed_expiry_count": expiry_count,
            "authority_backed_session_count": len(session_dates),
            "trade_count": len(trades),
            "blocker_count": len(blockers),
            "sealed_holdout_intent_count": sealed_holdout_intent_count,
            "intent_reconciliation": {
                "intent_count": len(intents),
                "trade_count": len(trades),
                "blocker_count": len(blockers),
                "sealed_holdout_intent_count": sealed_holdout_intent_count,
                "reconciled": len(trades) + len(blockers) + sealed_holdout_intent_count == len(intents),
            },
            "blocker_counts": dict(sorted(Counter(row["blocker_class"] for row in blockers).items())),
            "wfa_survivor_count": len(survivors),
            "holdout_authorized": bool(args.authorize_holdout),
            "holdout_outcomes_read": bool(args.authorize_holdout),
            "evaluation_overlay": {
                "max_hold_minutes": args.max_hold_minutes,
                "stop_loss_pct": args.stop_loss_pct,
                "target_pct": args.target_pct,
                "friction_bps_per_side": args.friction_bps_per_side,
                "friction_sensitivity_bps_per_side": list(FRICTION_SENSITIVITY_BPS),
                "minimum_partition_trades": args.minimum_partition_trades,
                "maximum_signal_to_entry_seconds": args.max_signal_to_entry_seconds,
                "maximum_expiry_metadata_gap_days": args.max_expiry_gap_days,
                "ambiguous_stop_target_bar_policy": "STOP_FIRST_CONSERVATIVE",
                "gap_through_stop_policy": "WORSE_OF_STOP_OR_BAR_OPEN_FOR_LONG_OPTION",
            },
            "metric_normalizations": list(NORMALIZATIONS),
            "atm_plus_minus_50_is_sensitivity_only": True,
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
            "Replay canonical TradeBot price-structure intents against real expired "
            "option minute candles with strict expiry, ATM, timing and authority gates."
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
        "--max-signal-to-entry-seconds",
        type=float,
        default=DEFAULT_MAX_SIGNAL_TO_ENTRY_SECONDS,
    )
    parser.add_argument(
        "--max-expiry-gap-days", type=int, default=DEFAULT_MAX_EXPIRY_GAP_DAYS
    )
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
