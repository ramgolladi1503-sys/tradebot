#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    canonical_json,
    sha256_file,
    write_json_with_sidecar,
)
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1.canonical_adapter import (
    CANONICAL_STRATEGIES,
)
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1.canonical_intent_campaign import (
    CanonicalIntentPolicy,
    generate_session_intents,
    policy_to_dict,
)
from research.option_e2e_recertification_v4.kite_underlying_directional_edge_campaign_v1.underlying_corpus import (
    audit_corpus,
    build_partitions,
)

INTENT_FIELDS = (
    "schema_version",
    "strategy_id",
    "candidate_strategy_id",
    "movement_type",
    "underlying",
    "signal_timestamp",
    "earliest_entry_timestamp",
    "direction",
    "signal_time_underlying_price",
    "intended_option_type",
    "intended_expiry_rule",
    "strike_rule",
    "strike_offset_steps",
    "signal_identity_hash",
    "partition",
    "candidate_status",
    "candidate_blockers",
    "candidate_warnings",
    "candidate_raw_score",
    "candidate_confidence_score",
    "candidate_price_structure_score",
    "entry_trigger",
    "invalid_if",
    "canonical_callable_identity",
    "canonical_callable_source_hash",
    "intent_status",
    "allowed_for_live_execution",
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


def run_campaign(
    kite_root: Path,
    output_root: Path,
    *,
    underlyings: tuple[str, ...] = ("NIFTY",),
    policy: CanonicalIntentPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or CanonicalIntentPolicy()
    requested_underlyings = tuple(
        sorted(
            {
                str(value).strip().upper()
                for value in underlyings
                if str(value).strip()
            }
        )
    )
    if not requested_underlyings:
        raise ValueError("at_least_one_underlying_required")

    sessions, by_file, by_session, rejected = audit_corpus(kite_root)
    partition_manifest = build_partitions(sessions)
    intents: list[dict[str, Any]] = []
    invocations: list[dict[str, Any]] = []

    for underlying in requested_underlyings:
        if underlying not in partition_manifest["indexes"]:
            invocations.append(
                {
                    "schema_version": "canonical_invocation_summary_v1",
                    "strategy_id": "*",
                    "underlying": underlying,
                    "session_date": "",
                    "partition": "",
                    "invocation_count": 0,
                    "candidate_count": 0,
                    "intent_count": 0,
                    "exception_count": 1,
                    "callable_identities": "[]",
                    "callable_source_hashes": "[]",
                    "exact_reasons": json.dumps(
                        [f"underlying_not_in_partition_manifest:{underlying}"]
                    ),
                    "holdout_outcomes_read": False,
                    "allowed_for_live_execution": False,
                }
            )
            continue
        index_partitions = partition_manifest["indexes"][underlying]
        part_by_date = {
            session_date: "development"
            for session_date in index_partitions["development_dates"]
        }
        part_by_date.update(
            {
                session_date: "validation"
                for session_date in index_partitions["validation_dates"]
            }
        )
        for session_date in (
            index_partitions["development_dates"]
            + index_partitions["validation_dates"]
        ):
            frame = sessions.get((session_date, underlying))
            if frame is None:
                continue
            partition = part_by_date[session_date]
            for strategy_key in sorted(CANONICAL_STRATEGIES):
                session_intents, summary = generate_session_intents(
                    strategy_key=strategy_key,
                    frame=frame,
                    session_date=session_date,
                    symbol=underlying,
                    partition=partition,
                    policy=policy,
                )
                intents.extend(session_intents)
                invocations.append(summary)

    intents = sorted(
        intents,
        key=lambda row: (
            row["signal_timestamp"],
            row["strategy_id"],
            row["signal_identity_hash"],
        ),
    )
    duplicate_hash_count = len(intents) - len(
        {row["signal_identity_hash"] for row in intents}
    )
    if duplicate_hash_count:
        raise ValueError(
            f"duplicate_canonical_signal_identity_hashes:{duplicate_hash_count}"
        )

    output_root.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_root / "canonical_option_intents.csv",
        intents,
        fieldnames=INTENT_FIELDS,
    )
    _write_csv(output_root / "canonical_invocation_summary.csv", invocations)
    _write_csv(output_root / "kite_underlying_authenticity_by_file.csv", by_file)
    _write_csv(output_root / "kite_underlying_authenticity_by_session.csv", by_session)
    write_json_with_sidecar(
        output_root / "kite_underlying_rejected_rows_summary.json", rejected
    )
    write_json_with_sidecar(
        output_root / "canonical_partition_manifest.json", partition_manifest
    )

    callable_hashes = sorted(
        {
            str(row["canonical_callable_source_hash"])
            for row in intents
            if row.get("canonical_callable_source_hash")
        }
    )
    exception_count = sum(int(row.get("exception_count") or 0) for row in invocations)
    candidate_count = sum(int(row.get("candidate_count") or 0) for row in invocations)
    invocation_count = sum(int(row.get("invocation_count") or 0) for row in invocations)
    manifest = {
        "schema_version": "canonical_option_intent_campaign_v1",
        "campaign": "CANONICAL_UNDERLYING_TO_OPTION_INTENT_CAMPAIGN_V1",
        "underlying_authority": "KITE_HISTORICAL_5MINUTE_OHLCV",
        "strategy_authority": "PRODUCTION_MOVEMENT_STRATEGY_CALLABLES",
        "strategy_keys": sorted(CANONICAL_STRATEGIES),
        "requested_underlyings": list(requested_underlyings),
        "policy": policy_to_dict(policy),
        "invocation_count": invocation_count,
        "candidate_count": candidate_count,
        "canonical_intent_count": len(intents),
        "invocation_exception_count": exception_count,
        "canonical_callable_source_hashes": callable_hashes,
        "duplicate_signal_identity_hash_count": duplicate_hash_count,
        "holdout_dates_present_but_not_invoked": True,
        "holdout_outcomes_read": False,
        "directional_proxy_pnl_computed": False,
        "option_pnl_computed": False,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "verdict": (
            "CANONICAL_INTENTS_READY_FOR_OPTION_REPLAY"
            if intents
            else "NO_CANONICAL_OPTION_INTENTS"
        ),
    }
    artifact_hashes = {
        path.name: f"sha256:{sha256_file(path)}"
        for path in output_root.iterdir()
        if path.is_file() and not path.name.endswith(".sha256")
    }
    manifest["artifact_hashes"] = artifact_hashes
    write_json_with_sidecar(output_root / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Invoke canonical TradeBot movement strategy owners on causal completed "
            "Kite five-minute bars and emit research-only option intents."
        )
    )
    parser.add_argument(
        "--kite-replay-root",
        type=Path,
        default=Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay"),
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--underlyings",
        default="NIFTY",
        help="Comma-separated underlying list; default matches the supplied NIFTY option corpus",
    )
    parser.add_argument("--minimum-completed-bars", type=int, default=2)
    parser.add_argument("--max-intents-per-strategy-session", type=int, default=1)
    args = parser.parse_args()
    policy = CanonicalIntentPolicy(
        minimum_completed_bars=args.minimum_completed_bars,
        max_intents_per_strategy_session=args.max_intents_per_strategy_session,
    )
    manifest = run_campaign(
        args.kite_replay_root.resolve(strict=True),
        args.output_root.resolve(),
        underlyings=tuple(args.underlyings.split(",")),
        policy=policy,
    )
    print(
        canonical_json(
            {
                key: manifest[key]
                for key in (
                    "campaign",
                    "verdict",
                    "invocation_count",
                    "canonical_intent_count",
                    "holdout_outcomes_read",
                )
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
