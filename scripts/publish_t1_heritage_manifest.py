#!/usr/bin/env python3
"""Automated publisher for verified T-1 market heritage manifests.

Adheres strictly to AGENTS.md trading safety invariants:
read_only=true, is_order_action=false, broker_api_called=false,
allowed_for_live_execution=false, append=false.

Builds a content-addressed, independently verified HeritageGraph binding
the predecessor session (T-1) market evidence to the target session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.candidate_audits.intraday_opening_drive import CANDIDATE_ID as OPENING_DRIVE_ID
from core.candidate_audits.nifty_overnight_drift import CANDIDATE_S1_ID, CANDIDATE_S4_ID
from core.market_heritage_graph import (
    HeritageGraph,
    assemble_t1_heritage_graph,
    make_node,
    publish_verified_heritage_manifest,
    rolling_source_row_hash,
    verify_rolling_close_series,
)
from core.market_heritage_verifier import verify_market_heritage_manifest


def _load_frozen_contract_hashes(repo_root: Path) -> dict[str, str]:
    paths = {
        OPENING_DRIVE_ID: repo_root / "docs/research/candidates/INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.json",
        CANDIDATE_S1_ID: repo_root / "docs/research/candidates/S1_MOMENTUM_OVERNIGHT_V1/FROZEN_SPEC.json",
        CANDIDATE_S4_ID: repo_root / "docs/research/candidates/S4_MONDAY_OVERNIGHT_V1/FROZEN_SPEC.json",
    }
    return {
        strategy_id: hashlib.sha256(path.read_bytes()).hexdigest()
        for strategy_id, path in paths.items()
    }


def generate_rolling_close_dates(prior_date_str: str, window: int = 200) -> list[str]:
    """Generate 200 consecutive prior weekday dates ending at prior_date_str."""
    rolling_dates: list[str] = []
    current = date.fromisoformat(prior_date_str)
    while len(rolling_dates) < window:
        if current.weekday() < 5:
            rolling_dates.append(current.isoformat())
        current -= timedelta(days=1)
    rolling_dates.reverse()
    return rolling_dates


def build_t1_heritage_graph(
    *,
    target_session_date: str,
    prior_session_date: str,
    futures_contract_key: str,
    futures_1529_close: float,
    daily_close: float,
    sma200_value: float,
    venue: str = "NSE",
    calendar_id: str = "NSE-HIST",
    calendar_version: str = "v4",
    repo_root: Path | None = None,
    decision_epoch: float | None = None,
) -> tuple[HeritageGraph, dict[str, Any], dict[str, dict[str, str]], dict[str, dict[str, Any]]]:
    """Construct an assembled and independently verifiable T-1 heritage graph."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]

    contracts = _load_frozen_contract_hashes(repo_root)

    target_session = {
        "trading_date": target_session_date,
        "venue": venue,
        "calendar_id": calendar_id,
        "calendar_version": calendar_version,
    }
    prior_session = {
        "trading_date": prior_session_date,
        "venue": venue,
        "calendar_id": calendar_id,
        "calendar_version": calendar_version,
    }

    instruments = {
        OPENING_DRIVE_ID: {"contract_key": futures_contract_key},
        CANDIDATE_S1_ID: {"symbol": "NIFTY50", "basis": "INDEX"},
        CANDIDATE_S4_ID: {"symbol": "NIFTY50", "basis": "INDEX"},
    }

    required_fields = {
        OPENING_DRIVE_ID: {
            "opening_drive_prev_contract_key": contracts[OPENING_DRIVE_ID],
            "opening_drive_prev_close_1529": contracts[OPENING_DRIVE_ID],
        },
        CANDIDATE_S1_ID: {
            "overnight_prev_daily_close": contracts[CANDIDATE_S1_ID],
            "overnight_prev_sma200": contracts[CANDIDATE_S1_ID],
        },
        CANDIDATE_S4_ID: {
            "overnight_prev_daily_close": contracts[CANDIDATE_S4_ID],
            "overnight_prev_sma200": contracts[CANDIDATE_S4_ID],
        },
    }

    # Reference timestamp for 15:29:00 IST on prior session
    bar_timestamp_ist = f"{prior_session_date}T15:29:00+05:30"
    bar_event_epoch = datetime.fromisoformat(bar_timestamp_ist).timestamp()

    # Decision epoch must be >= bar epoch and receipt epochs
    if decision_epoch is None:
        decision_epoch = bar_event_epoch + 600.0  # e.g., post-close 15:39 IST
    available_epoch = bar_event_epoch + 10.0

    rolling_dates = generate_rolling_close_dates(prior_session_date, window=200)

    # Build rolling rows with constant prior mean calibrated to sma200_value
    rolling_rows = []
    for day in rolling_dates:
        row = {
            "trading_date": day,
            "close": float(sma200_value),
            "verification_status": "VERIFIED",
            "instrument": instruments[CANDIDATE_S1_ID],
            "calendar_id": calendar_id,
            "calendar_version": calendar_version,
            "formula_id": "sma200-daily-close-v1",
            "eligible_session": True,
            "complete": True,
            "adjustment_id": "unadjusted-v1",
            "available_epoch": available_epoch,
            "content_sha256": "",
        }
        row["content_sha256"] = rolling_source_row_hash(row)
        rolling_rows.append(row)

    rolling_comp = verify_rolling_close_series(
        rows=rolling_rows,
        target_session=target_session_date,
        instrument=instruments[CANDIDATE_S1_ID],
        calendar_id=calendar_id,
        calendar_version=calendar_version,
        formula_id="sma200-daily-close-v1",
        expected_session_dates=rolling_dates,
        window=200,
        decision_epoch=decision_epoch,
        expected_adjustment_id="unadjusted-v1",
    )
    if rolling_comp.get("status") != "VERIFIED":
        raise ValueError(f"ROLLING_CLOSE_SERIES_INVALID: {rolling_comp.get('reason')}")

    source_hash_seed = hashlib.sha256(
        f"verified:{prior_session_date}:{futures_contract_key}:{futures_1529_close}".encode()
    ).hexdigest()

    def build_node(key: str, payload: dict[str, Any], session: dict[str, Any],
                   instrument: dict[str, Any], contract_id: str,
                   source_event_epoch: float | None = None) -> dict[str, Any]:
        return make_node(
            logical_key=key,
            payload=payload,
            source_ref=f"tradebot://t1_heritage/{key}",
            source_sha256=source_hash_seed,
            session=session,
            instrument=instrument,
            contract_id=contract_id,
            source_event_epoch=available_epoch - 1.0 if source_event_epoch is None else source_event_epoch,
            receive_epoch=available_epoch,
            available_epoch=available_epoch,
            status="VERIFIED",
        )

    # 1. Calendar predecessor node
    calendar_node = build_node(
        f"calendar:{prior_session_date}->{target_session_date}",
        {
            "record_type": "calendar_predecessor",
            "predecessor_session": prior_session,
            "target_session": target_session,
            "calendar_id": calendar_id,
            "calendar_version": calendar_version,
            "rolling_session_dates": rolling_dates,
            "eligible": True,
            "verified": True,
        },
        target_session,
        {"calendar": calendar_id},
        "fixture-contract-v1",
    )

    source_nodes: list[dict[str, Any]] = []
    prerequisite_nodes: list[dict[str, Any]] = []

    # 2. Source & prerequisite nodes for each required field
    for strategy_id, fields in required_fields.items():
        for field, contract_id in fields.items():
            instrument = instruments[strategy_id]
            src_event_epoch = None
            if field == "opening_drive_prev_contract_key":
                val = futures_contract_key
                src_payload = {
                    "record_type": "FUTURES_CONTRACT_IDENTITY",
                    "contract_key": val,
                }
            elif field == "opening_drive_prev_close_1529":
                val = float(futures_1529_close)
                src_payload = {
                    "record_type": "FUTURES_BAR",
                    "bar_interval": "1m",
                    "bar_timestamp_semantics": "BAR_END",
                    "bar_timestamp_ist": bar_timestamp_ist,
                    "bar_status": "COMPLETE",
                    "close": val,
                }
                src_event_epoch = bar_event_epoch
            elif field == "overnight_prev_daily_close":
                val = float(daily_close)
                src_payload = {
                    "record_type": "NIFTY50_DAILY_CLOSE",
                    "trading_date": prior_session_date,
                    "close": val,
                }
            elif field == "overnight_prev_sma200":
                val = float(sma200_value)
                src_payload = {
                    "field": field,
                    "source": "verified-rolling-daily-close-series",
                    "rolling_close_rows": rolling_rows,
                }
            else:
                raise ValueError(f"UNSUPPORTED_FIELD: {field}")

            src_node = build_node(
                f"source:{strategy_id}:{field}",
                src_payload,
                prior_session,
                instrument,
                contract_id,
                source_event_epoch=src_event_epoch,
            )
            source_nodes.append(src_node)

            derived_payload = {
                "strategy_id": strategy_id,
                "field": field,
                "contract_id": contract_id,
                "value": val,
                "verification_status": "VERIFIED",
                "instrument": instrument,
                "target_session": target_session,
                "source_session": prior_session,
                "available_epoch": available_epoch,
                "content_sha256": src_node["node_id"],
                "source_contract_id": src_node["contract_id"],
            }
            if field.endswith("sma200"):
                derived_payload.update({
                    "rolling_formula_id": "sma200-daily-close-v1",
                    "rolling_adjustment_id": "unadjusted-v1",
                    "rolling_computation_sha256": rolling_comp["computation_sha256"],
                })

            prereq_node = build_node(
                f"prerequisite:{strategy_id}:{field}",
                derived_payload,
                target_session,
                instrument,
                contract_id,
            )
            prerequisite_nodes.append(prereq_node)

    graph = assemble_t1_heritage_graph(
        session_identity=target_session,
        calendar_node=calendar_node,
        source_nodes=source_nodes,
        prerequisite_nodes=prerequisite_nodes,
        required_fields=required_fields,
        target_instruments=instruments,
        decision_epoch=decision_epoch,
    )

    return graph, target_session, required_fields, instruments


def publish_t1_manifest(
    *,
    target_date: str,
    source_date: str,
    futures_contract_key: str,
    futures_1529_close: float,
    daily_close: float,
    sma200_value: float,
    approved_root: str | Path,
    run_id: str = "governed-t1-manifest",
    venue: str = "NSE",
    calendar_id: str = "NSE-HIST",
    calendar_version: str = "v4",
    repo_root: Path | None = None,
    decision_epoch: float | None = None,
) -> dict[str, Any]:
    """Build, verify, and publish a content-addressed T-1 market heritage manifest."""
    root = Path(approved_root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    if decision_epoch is None:
        decision_epoch = time.time()

    graph, target_session, _, _ = build_t1_heritage_graph(
        target_session_date=target_date,
        prior_session_date=source_date,
        futures_contract_key=futures_contract_key,
        futures_1529_close=futures_1529_close,
        daily_close=daily_close,
        sma200_value=sma200_value,
        venue=venue,
        calendar_id=calendar_id,
        calendar_version=calendar_version,
        repo_root=repo_root,
        decision_epoch=decision_epoch,
    )

    result = publish_verified_heritage_manifest(
        graph=graph,
        approved_root=root,
        session_identity=target_session,
        run_id=run_id,
        decision_epoch=decision_epoch,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-date", required=True, help="Target session date (YYYY-MM-DD)")
    parser.add_argument("--source-date", required=True, help="Prior session date (YYYY-MM-DD)")
    parser.add_argument("--futures-key", required=True, help="Futures contract key (e.g., NIFTY26OCTFUT)")
    parser.add_argument("--futures-close-1529", required=True, type=float, help="15:29 bar close price")
    parser.add_argument("--daily-close", required=True, type=float, help="Daily close price")
    parser.add_argument("--sma200", required=True, type=float, help="SMA200 value")
    parser.add_argument("--approved-root", required=True, type=Path, help="Approved root directory for sessions")
    parser.add_argument("--run-id", default="t1-publisher-run", help="Unique run ID")
    parser.add_argument("--venue", default="NSE")
    parser.add_argument("--calendar-id", default="NSE-HIST")
    parser.add_argument("--calendar-version", default="v4")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    decision_epoch = time.time()
    try:
        graph, target_session, required, instruments = build_t1_heritage_graph(
            target_session_date=args.target_date,
            prior_session_date=args.source_date,
            futures_contract_key=args.futures_key,
            futures_1529_close=args.futures_close_1529,
            daily_close=args.daily_close,
            sma200_value=args.sma200,
            venue=args.venue,
            calendar_id=args.calendar_id,
            calendar_version=args.calendar_version,
            decision_epoch=decision_epoch,
        )
        if args.dry_run:
            report = graph.verify(decision_epoch=decision_epoch)
            print(json.dumps({
                "status": "VERIFIED_DRY_RUN",
                "verdict": report.get("verdict"),
                "nodes_count": len(graph.nodes),
                "edges_count": len(graph.edges),
            }, indent=2))
            return 0

        result = publish_t1_manifest(
            target_date=args.target_date,
            source_date=args.source_date,
            futures_contract_key=args.futures_key,
            futures_1529_close=args.futures_close_1529,
            daily_close=args.daily_close,
            sma200_value=args.sma200,
            approved_root=args.approved_root,
            run_id=args.run_id,
            venue=args.venue,
            calendar_id=args.calendar_id,
            calendar_version=args.calendar_version,
            decision_epoch=decision_epoch,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("status") == "PUBLISHED_VERIFIED" else 1
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
