#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.strategy_outcomes.artifacts import write_json_artifact  # noqa: E402
from research.strategy_outcomes.contract import HORIZONS_MINUTES, canonical_json_hash  # noqa: E402
from research.strategy_outcomes.engine import (  # noqa: E402
    BAR_TIMESTAMP_CONVENTION,
    CONTRACT_VERSION,
    apply_overlap,
    load_candidates,
    load_verified_sources,
    measure_candidate,
    outcome_records_hash,
)

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
        "schema_version": 3,
        "contract_version": CONTRACT_VERSION,
        "strategy_id": "opening_range_retest_v1",
        "mode": "RESEARCH_UNDERLYING_OUTCOME_MEASUREMENT",
        "entry_policy": "first_bar_after_proposal_ready_at",
        "bar_timestamp_convention": BAR_TIMESTAMP_CONVENTION,
        "horizon_policy": "elapsed_market_time_start_labelled_terminal_close",
        "horizons_minutes": list(HORIZONS_MINUTES),
        "stop_return": stop_return,
        "target_return": target_return,
        "same_bar_stop_target_policy": "AMBIGUOUS_SAME_BAR",
        "overlap_interval_convention": "[start,end)",
        "claim_boundary": "underlying_descriptive_outcomes_only",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _counter(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(sorted(Counter(str(record.get(key)) for record in records).items()))


def _horizon_status_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for horizon in HORIZONS_MINUTES:
        out[str(horizon)] = dict(
            sorted(Counter(str(record["horizons"][str(horizon)]["status"]) for record in records).items())
        )
    return out


def _path_event_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for horizon in HORIZONS_MINUTES:
        out[str(horizon)] = dict(
            sorted(Counter(str(record["horizons"][str(horizon)]["path_event"]) for record in records).items())
        )
    return out


def _write_artifacts(out_dir: Path, *, contract: dict[str, Any], records: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=False)
    paths = {
        "contract": out_dir / "opening_range_retest_outcome_contract_v1.json",
        "records": out_dir / "opening_range_retest_outcome_records_v1.json",
        "summary": out_dir / "opening_range_retest_outcome_summary_v1.json",
    }
    hashes = {
        "contract_hash": write_json_artifact(paths["contract"], contract),
        "records_artifact_hash": write_json_artifact(paths["records"], {"records": records}),
        "summary_hash": write_json_artifact(paths["summary"], summary),
    }
    for path in paths.values():
        digest = canonical_json_hash(json.loads(path.read_text(encoding="utf-8")))
        path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate corrected ORB underlying outcome artifacts.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--candidate-ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--source-manifest", type=Path, default=SOURCE_MANIFEST_PATH)
    parser.add_argument("--stop-return", type=float, default=0.001)
    parser.add_argument("--target-return", type=float, default=0.002)
    args = parser.parse_args()

    ledger = _load_json(args.candidate_ledger)
    source_manifest = _load_json(args.source_manifest)
    candidates = load_candidates(ledger)
    if ledger.get("candidate_count") != EXPECTED_CANDIDATE_COUNT or len(candidates) != EXPECTED_CANDIDATE_COUNT:
        raise SystemExit("certified_candidate_count_mismatch")
    if ledger.get("candidate_semantic_hash") != EXPECTED_CANDIDATE_HASH:
        raise SystemExit("certified_candidate_hash_mismatch")
    if len(source_manifest.get("records") or []) != EXPECTED_SOURCE_COUNT:
        raise SystemExit("certified_source_count_mismatch")
    if dict(source_manifest.get("selection_summary") or {}).get("semantic_hash") != EXPECTED_SOURCE_HASH:
        raise SystemExit("certified_source_hash_mismatch")

    sources = load_verified_sources(PROJECT_ROOT, source_manifest)
    records = [
        measure_candidate(
            candidate,
            source=sources.get(candidate.session_key),
            stop_return=args.stop_return,
            target_return=args.target_return,
        )
        for candidate in candidates
    ]
    overlap_summary = apply_overlap(records)
    record_hash = outcome_records_hash(records)
    summary = {
        "schema_version": 3,
        "contract_version": CONTRACT_VERSION,
        "decision": "ORB_OUTCOMES_MEASURED",
        "mode": "RESEARCH_UNDERLYING_OUTCOME_MEASUREMENT",
        "strategy_id": "opening_range_retest_v1",
        "code_sha": _git_sha(),
        "candidate_count": len(records),
        "candidate_semantic_hash": EXPECTED_CANDIDATE_HASH,
        "source_count": len(sources),
        "source_universe_hash": EXPECTED_SOURCE_HASH,
        "certified_merged_main_summary_hash": EXPECTED_SUMMARY_HASH,
        "source_files_byte_verified": len(sources),
        "candidate_status_counts": _counter(records, "candidate_status"),
        "horizon_status_counts": _horizon_status_counts(records),
        "path_event_counts": _path_event_counts(records),
        "overlap_counts": overlap_summary,
        "candidate_record_semantic_hash": record_hash,
        "strategy_semantic_summary_hash": canonical_json_hash(
            {
                "candidate_count": len(records),
                "candidate_record_semantic_hash": record_hash,
                "candidate_status_counts": _counter(records, "candidate_status"),
                "horizon_status_counts": _horizon_status_counts(records),
                "overlap_counts": overlap_summary,
                "path_event_counts": _path_event_counts(records),
            }
        ),
        "bar_timestamp_convention": BAR_TIMESTAMP_CONVENTION,
        "horizon_policy": "elapsed_market_time_start_labelled_terminal_close",
        "claim_boundary": "underlying_descriptive_outcomes_only",
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    contract = _contract_payload(stop_return=args.stop_return, target_return=args.target_return)
    hashes = _write_artifacts(args.out_dir, contract=contract, records=records, summary=summary)
    summary.update(hashes)
    write_json_artifact(args.out_dir / "opening_range_retest_outcome_summary_v1.json", summary)
    (args.out_dir / "opening_range_retest_outcome_summary_v1.json.sha256").write_text(
        f"{canonical_json_hash(summary)}  opening_range_retest_outcome_summary_v1.json\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "verdict": summary["decision"],
                "candidate_count": len(records),
                "candidate_record_semantic_hash": record_hash,
                "strategy_semantic_summary_hash": summary["strategy_semantic_summary_hash"],
                "summary_hash": canonical_json_hash(summary),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
