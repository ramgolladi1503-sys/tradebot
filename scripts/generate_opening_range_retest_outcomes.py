#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from research.strategy_outcomes.adapters.opening_range_retest import (  # noqa: E402
    bars_from_ohlcv_rows,
    candidate_from_orb_ledger_row,
    canonical_outcome_records_hash,
)
from research.strategy_outcomes.artifacts import write_json_artifact  # noqa: E402
from research.strategy_outcomes.contract import HORIZONS_MINUTES, OutcomeCandidate  # noqa: E402
from research.strategy_outcomes.exposure import duplicate_directional_exposure  # noqa: E402
from research.strategy_outcomes.excursions import mfe_mae  # noqa: E402
from research.strategy_outcomes.forward_returns import forward_returns, legal_entry_index  # noqa: E402
from research.strategy_outcomes.oracle import validate_bar_sequence  # noqa: E402
from research.strategy_outcomes.path_events import stop_target_event  # noqa: E402

EXPECTED_CANDIDATE_COUNT = 2215
EXPECTED_CANDIDATE_HASH = "53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24"
EXPECTED_SOURCE_COUNT = 1512
EXPECTED_SOURCE_HASH = "cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc"
EXPECTED_SUMMARY_HASH = "34b7c8628e28c436a2b18a1d9598077d2e08e0eab09009748e06c2ed41eb9074"
LEDGER_PATH = Path("docs/agent_reviews/opening_range_retest_causal_replay_candidate_ledger_v1.json")
SOURCE_MANIFEST_PATH = Path("docs/agent_reviews/opening_range_retest_causal_replay_source_manifest_v1.json")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()


def _contract_payload(*, stop_return: float, target_return: float) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "strategy_id": "opening_range_retest_v1",
        "mode": "RESEARCH_UNDERLYING_OUTCOME_MEASUREMENT",
        "entry_policy": "first_bar_after_proposal_ready_at",
        "horizons_minutes": list(HORIZONS_MINUTES),
        "stop_return": stop_return,
        "target_return": target_return,
        "same_bar_stop_target_policy": "AMBIGUOUS_SAME_BAR",
        "claim_boundary": "underlying_descriptive_outcomes_only",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _source_key(record: dict[str, Any]) -> str:
    return f"{record.get('session_date')}:{str(record.get('symbol') or '').upper()}"


def _load_bars_by_key(source_manifest: dict[str, Any]) -> dict[str, list[Any]]:
    by_key: dict[str, list[Any]] = {}
    for source in source_manifest.get("records") or []:
        path = PROJECT_ROOT / str(source["logical_path"])
        if not path.exists():
            path = Path(str(source["absolute_path"]))
        frame = pd.read_parquet(path, columns=["timestamp", "open", "high", "low", "close"])
        bars = bars_from_ohlcv_rows(frame.to_dict(orient="records"), session_key=_source_key(source))
        validate_bar_sequence(bars)
        by_key[_source_key(source)] = bars
    return by_key


def _candidate_status(candidate: OutcomeCandidate, bars_by_key: dict[str, list[Any]]) -> tuple[str, str, list[Any]]:
    bars = bars_by_key.get(candidate.session_key)
    if not bars:
        return "NO_SOURCE_BARS", "source_session_symbol_missing", []
    if legal_entry_index(bars, candidate.proposal_ready_at) is None:
        return "NO_LEGAL_ENTRY", "no_bar_strictly_after_proposal_ready_at", bars
    return "MEASURED", "ok", bars


def _empty_horizon_map(value: Any) -> dict[str, Any]:
    return {str(horizon): value for horizon in HORIZONS_MINUTES}


def _measure_candidate(
    candidate: OutcomeCandidate,
    *,
    bars_by_key: dict[str, list[Any]],
    stop_return: float,
    target_return: float,
) -> dict[str, Any]:
    status, reason, bars = _candidate_status(candidate, bars_by_key)
    entry_index = legal_entry_index(bars, candidate.proposal_ready_at) if bars else None
    entry_bar = bars[entry_index] if entry_index is not None else None
    record: dict[str, Any] = {
        "candidate_id": candidate.candidate_id,
        "candidate_hash": candidate.candidate_hash,
        "session_key": candidate.session_key,
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "proposal_ready_at": candidate.proposal_ready_at,
        "status": status,
        "reason": reason,
        "entry_policy": "first_bar_after_proposal_ready_at",
        "entry_timestamp": entry_bar.timestamp if entry_bar else None,
        "entry_price": entry_bar.open if entry_bar else None,
        "forward_returns": _empty_horizon_map(None),
        "mfe_mae": _empty_horizon_map({"mfe": None, "mae": None, "time_to_mfe": None, "time_to_mae": None}),
        "path_events": _empty_horizon_map("NOT_MEASURED"),
    }
    if status != "MEASURED":
        return record
    record["forward_returns"] = forward_returns(candidate, bars)
    record["mfe_mae"] = {str(horizon): mfe_mae(candidate, bars, horizon=horizon) for horizon in HORIZONS_MINUTES}
    record["path_events"] = {
        str(horizon): stop_target_event(candidate, bars, stop_return=stop_return, target_return=target_return, horizon=horizon)
        for horizon in HORIZONS_MINUTES
    }
    return record


def _summarize(records: list[dict[str, Any]], *, code_sha: str, stop_return: float, target_return: float) -> dict[str, Any]:
    statuses: dict[str, int] = {}
    path_event_counts: dict[str, dict[str, int]] = {str(horizon): {} for horizon in HORIZONS_MINUTES}
    for record in records:
        statuses[str(record["status"])] = statuses.get(str(record["status"]), 0) + 1
        for horizon, event in dict(record["path_events"]).items():
            bucket = path_event_counts.setdefault(str(horizon), {})
            bucket[str(event)] = bucket.get(str(event), 0) + 1
    return {
        "schema_version": 2,
        "decision": "ORB_OUTCOMES_MEASURED",
        "mode": "RESEARCH_UNDERLYING_OUTCOME_MEASUREMENT",
        "strategy_id": "opening_range_retest_v1",
        "code_sha": code_sha,
        "source_count": EXPECTED_SOURCE_COUNT,
        "source_universe_hash": EXPECTED_SOURCE_HASH,
        "candidate_count": len(records),
        "candidate_semantic_hash": EXPECTED_CANDIDATE_HASH,
        "certified_merged_main_summary_hash": EXPECTED_SUMMARY_HASH,
        "outcome_semantic_hash": canonical_outcome_records_hash(records),
        "status_counts": dict(sorted(statuses.items())),
        "path_event_counts": {key: dict(sorted(value.items())) for key, value in sorted(path_event_counts.items())},
        "stop_return": stop_return,
        "target_return": target_return,
        "claim_boundary": "underlying_descriptive_outcomes_only",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ORB underlying outcome artifacts.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--candidate-ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--source-manifest", type=Path, default=SOURCE_MANIFEST_PATH)
    parser.add_argument("--stop-return", type=float, default=0.001)
    parser.add_argument("--target-return", type=float, default=0.002)
    args = parser.parse_args()

    ledger = _load_json(args.candidate_ledger)
    source_manifest = _load_json(args.source_manifest)
    candidates = [candidate_from_orb_ledger_row(row) for row in ledger.get("records") or []]
    if ledger.get("candidate_count") != EXPECTED_CANDIDATE_COUNT or len(candidates) != EXPECTED_CANDIDATE_COUNT:
        raise SystemExit("certified_candidate_count_mismatch")
    if ledger.get("candidate_semantic_hash") != EXPECTED_CANDIDATE_HASH:
        raise SystemExit("certified_candidate_hash_mismatch")
    if len(source_manifest.get("records") or []) != EXPECTED_SOURCE_COUNT:
        raise SystemExit("certified_source_count_mismatch")
    if dict(source_manifest.get("selection_summary") or {}).get("semantic_hash") != EXPECTED_SOURCE_HASH:
        raise SystemExit("certified_source_hash_mismatch")

    bars_by_key = _load_bars_by_key(source_manifest)
    records = [
        _measure_candidate(candidate, bars_by_key=bars_by_key, stop_return=args.stop_return, target_return=args.target_return)
        for candidate in candidates
    ]
    summary = _summarize(records, code_sha=_git_sha(), stop_return=args.stop_return, target_return=args.target_return)
    duplicates = duplicate_directional_exposure(candidates)
    summary["duplicate_directional_exposure_count"] = len(duplicates)
    summary["duplicate_directional_exposures"] = list(duplicates[:100])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    contract_hash = write_json_artifact(
        args.out_dir / "opening_range_retest_outcome_contract_v1.json",
        _contract_payload(stop_return=args.stop_return, target_return=args.target_return),
    )
    records_hash = write_json_artifact(args.out_dir / "opening_range_retest_outcome_records_v1.json", {"records": records})
    summary["contract_hash"] = contract_hash
    summary["records_artifact_hash"] = records_hash
    summary_hash = write_json_artifact(args.out_dir / "opening_range_retest_outcome_summary_v1.json", summary)
    print(
        json.dumps(
            {
                "verdict": summary["decision"],
                "candidate_count": len(records),
                "outcome_semantic_hash": summary["outcome_semantic_hash"],
                "summary_hash": summary_hash,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
