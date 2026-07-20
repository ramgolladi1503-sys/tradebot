from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "research" / "opening_range_retest_corrected_score_edge"
BASELINE_SHA = "a48176fc245375f15e316493364915ec37439e29"
CORRECTED_SHA = "cf1b63908c779db844ef3534804142a8af26cbac"
SOURCE_MANIFEST = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_causal_replay_source_manifest_v2.json"
CANDIDATE_LEDGER = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_causal_replay_candidate_ledger_v2.json"
OUTCOME_LEDGER = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_outcome_ledger_v2.json"
OUTCOME_SUMMARY = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_outcome_summary_v2.json"
OUTCOME_CONTRACT = PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_outcome_contract_v2.json"
TIMESTAMP = "2026-07-21T00:00:00Z"
AUTHORIZED_RESEARCH_PATH_PREFIXES = (
    "research/opening_range_retest_corrected_score_edge/",
    "scripts/run_opening_range_retest_corrected_score_edge.py",
    "scripts/audit_opening_range_retest_corrected_score_edge.py",
    "tests/test_opening_range_retest_corrected_score_edge.py",
)
PRODUCTION_PATH_PREFIXES = (
    "strategies/",
    "core/",
    "config/",
    "execution/",
    "risk/",
    "feeds/",
)
VOLATILE_DETERMINISM_KEYS = {"absolute_output_dir", "execution_timestamp", "physical_temporary_path"}


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json_bytes(payload) + b"\n"
    path.write_bytes(data)
    digest = sha256_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    digest = sha256_file(path)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def git_output(args: list[str]) -> str:
    return subprocess.run(args, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True).stdout.strip()


def git_success(args: list[str]) -> bool:
    return subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True, text=True).returncode == 0


def safety_fields() -> dict[str, bool]:
    return {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def is_authorized_research_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in AUTHORIZED_RESEARCH_PATH_PREFIXES)


def is_production_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in PRODUCTION_PATH_PREFIXES)


def verify_source_identity() -> dict[str, Any]:
    research_head = git_output(["git", "rev-parse", "HEAD"])
    branch = git_output(["git", "branch", "--show-current"])
    ancestor_ok = git_success(["git", "merge-base", "--is-ancestor", CORRECTED_SHA, research_head])
    changed_paths = [
        line.strip()
        for line in git_output(["git", "diff", "--name-only", f"{CORRECTED_SHA}..HEAD"]).splitlines()
        if line.strip()
    ]
    unauthorized_paths = [path for path in changed_paths if not is_authorized_research_path(path)]
    production_changed_paths = [path for path in changed_paths if is_production_path(path)]
    working_production_diffs = [
        line.strip()
        for line in git_output(["git", "diff", "--name-only", CORRECTED_SHA, "--", *PRODUCTION_PATH_PREFIXES]).splitlines()
        if line.strip()
    ]
    status = {
        "schema_version": 1,
        "validated_production_source_sha": CORRECTED_SHA,
        "research_execution_head": research_head,
        "research_branch": branch,
        "source_ancestor_check": "PASS" if ancestor_ok else "FAIL",
        "changed_paths_since_validated_source": changed_paths,
        "unauthorized_changed_paths_since_validated_source": unauthorized_paths,
        "production_changed_paths_since_validated_source": production_changed_paths,
        "working_tree_production_diffs_vs_validated_source": working_production_diffs,
        **safety_fields(),
    }
    status["decision"] = "PASS" if ancestor_ok and not unauthorized_paths and not production_changed_paths and not working_production_diffs else "FAIL"
    if status["decision"] != "PASS":
        raise RuntimeError(f"SOURCE_IDENTITY_GATE_FAILED {json.dumps(status, sort_keys=True)}")
    return status


def stable_hash(records: list[dict[str, Any]], fields: list[str]) -> str:
    projected = [{field: record.get(field) for field in fields} for record in records]
    return sha256_bytes(canonical_json_bytes(projected))


def candidate_records() -> list[dict[str, Any]]:
    payload = read_json(CANDIDATE_LEDGER)
    return [dict(item["candidate_core"], candidate_id=item["candidate_id"]) for item in payload["records"]]


def outcome_records() -> list[dict[str, Any]]:
    payload = read_json(OUTCOME_LEDGER)
    return payload["records"]


def asset_summary(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    if path.suffix == ".json" and path.exists():
        payload = read_json(path)
    records = payload.get("records", []) if isinstance(payload, dict) else []
    candidate_count = payload.get("candidate_count") if isinstance(payload, dict) else None
    session_values: list[str] = []
    symbol_values: list[str] = []
    direction_counts: Counter[str] = Counter()
    for record in records:
        core = record.get("candidate_core", record)
        session = core.get("session_date") or record.get("source_session_date")
        symbol = core.get("symbol") or record.get("source_symbol")
        direction = core.get("direction")
        if session:
            session_values.append(str(session))
        if symbol:
            symbol_values.append(str(symbol))
        if direction:
            direction_counts[str(direction)] += 1
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "file_type": path.suffix.lstrip(".") or "unknown",
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "row_count": len(records) if records else None,
        "candidate_count": candidate_count,
        "session_count": len(set(session_values)) if session_values else None,
        "date_range": [min(session_values), max(session_values)] if session_values else None,
        "instrument_universe": sorted(set(symbol_values)),
        "call_count": direction_counts.get("BUY_CALL", 0),
        "put_count": direction_counts.get("BUY_PUT", 0),
        "source_commit": payload.get("execution_commit_sha") or payload.get("frozen_code_sha") if isinstance(payload, dict) else None,
        "contract_version": payload.get("contract_version") or payload.get("mode") if isinstance(payload, dict) else None,
        "contains_real_option_bid_ask": False,
        "contains_ltp_only": False,
        "underlying_only": path in {OUTCOME_LEDGER, OUTCOME_SUMMARY, OUTCOME_CONTRACT},
        "pre_cost": path in {OUTCOME_LEDGER, OUTCOME_SUMMARY, OUTCOME_CONTRACT},
        "independently_audited": (PROJECT_ROOT / "docs" / "agent_reviews" / "opening_range_retest_outcome_audit_v2.json").exists(),
        "eligible_for_this_validation": path in {SOURCE_MANIFEST, CANDIDATE_LEDGER, OUTCOME_LEDGER, OUTCOME_SUMMARY, OUTCOME_CONTRACT},
    }


def build_contract() -> dict[str, Any]:
    sessions = sorted({record["session_date"] for record in candidate_records()})
    split_index = math.floor(len(sessions) * 0.8)
    contract = {
        "schema_version": 1,
        "mode": "ORB_CORRECTED_SCORE_STRUCTURAL_EDGE_REVALIDATION",
        "decision": "EDGE_VALIDATION_CONTRACT_FROZEN",
        "timestamp": TIMESTAMP,
        "source": "corrected PR 682 head",
        "historical_implementation": BASELINE_SHA,
        "corrected_implementation": CORRECTED_SHA,
        "primary_hypotheses": ["H1_CANDIDATE_EDGE", "H2_SCORE_DISCRIMINATION", "H3_TOP_BUCKET_EDGE"],
        "primary_metrics": [
            "all-candidate net expectancy",
            "top-20%-score net expectancy",
            "top-minus-bottom score-quintile expectancy spread",
            "corrected-score versus old-score ranking lift",
            "session-clustered bootstrap confidence intervals",
            "profit factor",
            "median trade return",
            "win rate",
            "maximum drawdown",
            "session concentration",
            "CALL/PUT breakdown",
            "regime breakdown",
            "expiry-distance breakdown",
        ],
        "primary_ranking_bucket": "top 20% of corrected raw scores within each development/WFA selection universe",
        "chronological_split": {
            "split_unit": "whole trading session",
            "random_split": "forbidden",
            "development_session_count": split_index,
            "holdout_session_count": len(sessions) - split_index,
            "development_start": sessions[0] if sessions else None,
            "development_end": sessions[split_index - 1] if split_index else None,
            "holdout_start": sessions[split_index] if split_index < len(sessions) else None,
            "holdout_end": sessions[-1] if sessions else None,
            "purge_embargo": "zero only because certified ORB v2 outcomes are intraday and terminal horizons remain within each source session",
        },
        "cost_and_execution_authority": {
            "entry": "real ask required",
            "exit": "real bid required",
            "forbidden": [
                "LTP-only executable pricing",
                "synthetic bid/ask",
                "forward-filled executable quotes",
                "fallback executable quotes",
                "stale executable quotes",
                "missing executable quotes",
                "crossed-market executable quotes",
            ],
            "status": "NO_TRUSTED_OPTION_BID_ASK_LEDGER_FOUND",
        },
        "minimum_evidence_requirements": {
            "eligible_candidates": 300,
            "independent_sessions": 50,
            "primary_top_score_bucket_trades": 100,
            "meaningful_call_and_put_representation": True,
            "max_single_session_net_pnl_fraction": 0.2,
        },
        **safety_fields(),
    }
    contract["contract_hash"] = sha256_bytes(canonical_json_bytes({k: v for k, v in contract.items() if k != "contract_hash"}))
    return contract


def build_dataset_manifest(contract_hash: str) -> dict[str, Any]:
    paths = [SOURCE_MANIFEST, CANDIDATE_LEDGER, OUTCOME_LEDGER, OUTCOME_SUMMARY, OUTCOME_CONTRACT]
    manifest = {
        "schema_version": 1,
        "mode": "ORB_CORRECTED_SCORE_EDGE_DATASET_MANIFEST",
        "decision": "DATASET_MANIFEST_FROZEN",
        "timestamp": TIMESTAMP,
        "contract_hash": contract_hash,
        "asset_count": len(paths),
        "assets": [asset_summary(path) for path in paths],
        "trusted_option_bid_ask_available": False,
        "option_data_search_result": "No artifact tied to the 2215-candidate ORB Phase 1 universe contains trusted executable entry ask and exit bid with costs.",
        **safety_fields(),
    }
    manifest["dataset_manifest_hash"] = sha256_bytes(canonical_json_bytes({k: v for k, v in manifest.items() if k != "dataset_manifest_hash"}))
    return manifest


def build_candidate_conservation() -> dict[str, Any]:
    records = candidate_records()
    fields = [
        "candidate_id",
        "setup_id",
        "strategy_id",
        "symbol",
        "session_date",
        "direction",
        "boundary_type",
        "normalized_boundary",
        "breakout_timestamp",
        "retest_timestamp",
        "continuation_timestamp",
        "proposal_ready_at_iso",
        "history_hash",
        "entry_trigger",
        "invalid_if",
        "status",
    ]
    return {
        "schema_version": 1,
        "mode": "CANDIDATE_CONSERVATION_ORACLE",
        "decision": "NOT_EVALUATED_DUAL_REPLAY_UNAVAILABLE",
        "reason": "No authoritative dual-version replay entry point was available in this compact repair; the baseline ledger was not regenerated from a48176f and must not be inferred from the corrected ledger.",
        "baseline_implementation": BASELINE_SHA,
        "corrected_implementation": CORRECTED_SHA,
        "base_candidate_count": None,
        "corrected_candidate_count": len(records),
        "current_certified_candidate_count": len(records),
        "candidate_id_count": len({record["candidate_id"] for record in records}),
        "non_score_candidate_differences": None,
        "candidate_semantic_hash": stable_hash(records, fields),
        "exact_comparison_count": None,
        "field_level_diff_report": None,
        "distinct_generated_ledger_paths": [],
        "source_shas_compared": [],
        "ledger_sha256_values": [],
        "exact_conservation_fields": fields,
        "permitted_differences": [
            "raw_score",
            "retest_distance_pct",
            "retest_distance_source",
            "breakout_distance_pct evidence separation",
            "breakout/retest/continuation evidence fields",
        ],
        "hard_limit": "No economic claim is made because trusted option bid/ask data is unavailable.",
        **safety_fields(),
    }


def build_outcome_invariance() -> dict[str, Any]:
    outcomes = outcome_records()
    candidate_ids = [record["candidate_id"] for record in outcomes]
    return {
        "schema_version": 1,
        "mode": "OUTCOME_INVARIANCE_ORACLE",
        "decision": "OPTION_ECONOMIC_OUTCOME_INVARIANCE_NOT_EVALUABLE_NO_TRUSTED_OPTION_DATA",
        "reason": "Existing outcome ledger is descriptive underlying-only; before/after option entry, exit, and cost invariance cannot be evaluated without a trusted option trade ledger.",
        "candidate_count": len(candidate_ids),
        "duplicate_candidate_ids": len(candidate_ids) - len(set(candidate_ids)),
        "underlying_outcome_ledger_hash": read_json(OUTCOME_LEDGER).get("outcome_ledger_hash"),
        "underlying_outcome_invariance": "NOT_EVALUATED",
        "underlying_outcome_invariance_reason": "Only the corrected-head certified underlying ledger is present; no historical before/after underlying outcome ledger was regenerated in this task.",
        "option_invariance_available": False,
        "option_economic_outcome_invariance": "NOT_EVALUABLE_NO_TRUSTED_OPTION_DATA",
        **safety_fields(),
    }


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 12) if values else None


def build_underlying_summary() -> dict[str, Any]:
    summary = read_json(OUTCOME_SUMMARY)
    stats = summary.get("descriptive_directional_return_stats", {})
    return {
        "schema_version": 1,
        "mode": "UNDERLYING_STRUCTURAL_SIGNAL_SUMMARY",
        "decision": "UNDERLYING_SIGNAL_EVALUATION_INCOMPLETE",
        "reason": "Certified ORB v2 outcome summary has horizon returns, candidate counts, and session counts, but this task did not compute chronological fold results, holdout results, session-cluster uncertainty, negative controls, and concentration analysis for an underlying-signal claim.",
        "candidate_count": summary.get("candidate_count"),
        "session_count": len({record["candidate_core"]["session_date"] for record in outcome_records()}),
        "horizon_status_counts": summary.get("horizon_status_counts"),
        "directional_return_means": {horizon: values.get("mean") for horizon, values in stats.items()},
        "directional_return_medians": {horizon: values.get("median") for horizon, values in stats.items()},
        "mfe_means": {horizon: values.get("mfe", {}).get("mean") for horizon, values in stats.items()},
        "mae_means": {horizon: values.get("mae", {}).get("mean") for horizon, values in stats.items()},
        "chronological_fold_results": "NOT_CALCULATED",
        "holdout_results": "NOT_CALCULATED",
        "session_cluster_uncertainty": "NOT_CALCULATED",
        "negative_controls": "NOT_CALCULATED",
        "concentration_analysis": "NOT_CALCULATED",
        "claim_boundary": summary.get("claim_boundary"),
        **safety_fields(),
    }


def build_score_summary() -> dict[str, Any]:
    records = candidate_records()
    scores = [float(record["raw_score"]) for record in records if record.get("raw_score") is not None]
    by_direction: dict[str, list[float]] = defaultdict(list)
    for record in records:
        by_direction[str(record["direction"])].append(float(record["raw_score"]))
    return {
        "schema_version": 1,
        "mode": "SCORE_DISCRIMINATION_SUMMARY",
        "decision": "BLOCKED_BY_MISSING_TRUSTED_OPTION_DATA",
        "candidate_count": len(records),
        "historical_score_summary": "not recomputed; candidate-economic comparison blocked before option outcomes",
        "corrected_score_summary": {
            "count": len(scores),
            "min": min(scores),
            "max": max(scores),
            "mean": _mean(scores),
            "median": round(statistics.median(scores), 12) if scores else None,
            "by_direction_mean": {direction: _mean(values) for direction, values in sorted(by_direction.items())},
        },
        "score_delta_summary": "not computed against executable option outcomes",
        "corrected_versus_historical_lift": None,
        **safety_fields(),
    }


def build_empty_gate_artifact(mode: str, decision: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": mode,
        "decision": decision,
        "reason": reason,
        "fold_count": 0 if "WFA" in mode else None,
        "result_count": 0,
        **safety_fields(),
    }


def build_external_artifact_manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "ORB_CORRECTED_SCORE_EXTERNAL_ARTIFACT_MANIFEST",
        "decision": "ARTIFACT_AVAILABILITY_RECORDED",
        "reason": "No Parquet ledger is generated unless authoritative inputs exist. Missing ledgers are represented as unavailable metadata, not empty placeholder files.",
        "artifact_count": 0,
        "available_artifacts": [],
        "unavailable_artifacts": [
            {
                "logical_artifact_name": "old_vs_corrected_score_ledger",
                "expected_format": "parquet",
                "status": "NOT_GENERATED_DUAL_REPLAY_MISSING",
                "path": None,
                "size_bytes": None,
                "sha256": None,
                "row_count": None,
                "reason": "A genuine baseline-versus-corrected dual replay was not executed; no baseline ledger is inferred from the corrected ledger.",
            },
            {
                "logical_artifact_name": "option_trade_ledger",
                "expected_format": "parquet",
                "status": "NOT_GENERATED_NO_TRUSTED_OPTION_BID_ASK",
                "path": None,
                "size_bytes": None,
                "sha256": None,
                "row_count": None,
                "reason": "No trusted executable option bid/ask ledger exists for entry ask, exit bid, and cost economics on the frozen ORB candidate universe.",
            },
        ],
        **safety_fields(),
    }


def stable_projection(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: stable_projection(value) for key, value in sorted(payload.items()) if key not in VOLATILE_DETERMINISM_KEYS}
    if isinstance(payload, list):
        return [stable_projection(item) for item in payload]
    return payload


def compact_artifact_hashes(output_dir: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(output_dir.glob("*.json")):
        if path.name in {"determinism_report.json", "artifact_audit.json"}:
            continue
        hashes[path.name] = sha256_bytes(canonical_json_bytes(stable_projection(read_json(path))))
    return hashes


def compare_outputs(run_a: Path, run_b: Path) -> dict[str, Any]:
    hash_a = compact_artifact_hashes(run_a)
    hash_b = compact_artifact_hashes(run_b)
    differing = sorted(set(hash_a) ^ set(hash_b))
    differing.extend(name for name in sorted(set(hash_a) & set(hash_b)) if hash_a[name] != hash_b[name])
    external_a = read_json(run_a / "external_artifact_manifest.json")
    external_b = read_json(run_b / "external_artifact_manifest.json")
    final_a = read_json(run_a / "final_verdict.json")
    final_b = read_json(run_b / "final_verdict.json")
    result = {
        "schema_version": 1,
        "mode": "DETERMINISM_REPORT",
        "decision": "PASS" if not differing else "FAIL",
        "run_a": str(run_a),
        "run_b": str(run_b),
        "run_a_hash": sha256_bytes(canonical_json_bytes(hash_a)),
        "run_b_hash": sha256_bytes(canonical_json_bytes(hash_b)),
        "comparison_result": "PASS" if not differing else "FAIL",
        "differing_artifacts": differing,
        "differing_json_paths": [],
        "contract_semantic_hash_run_a": hash_a.get("edge_validation_contract.json"),
        "contract_semantic_hash_run_b": hash_b.get("edge_validation_contract.json"),
        "dataset_manifest_semantic_hash_run_a": hash_a.get("dataset_manifest.json"),
        "dataset_manifest_semantic_hash_run_b": hash_b.get("dataset_manifest.json"),
        "candidate_artifact_semantic_hash_run_a": hash_a.get("candidate_conservation.json"),
        "candidate_artifact_semantic_hash_run_b": hash_b.get("candidate_conservation.json"),
        "unavailable_artifact_classifications_run_a": [item["status"] for item in external_a.get("unavailable_artifacts", [])],
        "unavailable_artifact_classifications_run_b": [item["status"] for item in external_b.get("unavailable_artifacts", [])],
        "final_verdict_semantic_hash_run_a": hash_a.get("final_verdict.json"),
        "final_verdict_semantic_hash_run_b": hash_b.get("final_verdict.json"),
        "compact_artifact_hashes_run_a": hash_a,
        "compact_artifact_hashes_run_b": hash_b,
        "old_vs_corrected_score_ledger": "NOT_APPLICABLE_ARTIFACT_UNAVAILABLE",
        "option_trade_ledger": "NOT_APPLICABLE_ARTIFACT_UNAVAILABLE",
        "final_verdict_run_a": final_a.get("final_verdict"),
        "final_verdict_run_b": final_b.get("final_verdict"),
        **safety_fields(),
    }
    result["determinism_hash"] = sha256_bytes(canonical_json_bytes({k: v for k, v in result.items() if k != "determinism_hash"}))
    return result


def build_final_verdict(contract_hash: str, manifest_hash: str, determinism_hash: str, source_identity: dict[str, Any]) -> dict[str, Any]:
    candidates = candidate_records()
    sessions = sorted({record["session_date"] for record in candidates})
    directions = Counter(record["direction"] for record in candidates)
    conservation = build_candidate_conservation()
    return {
        "schema_version": 1,
        "mode": "ORB_CORRECTED_SCORE_STRUCTURAL_EDGE_REVALIDATION_FINAL",
        **safety_fields(),
        "final_verdict": "INSUFFICIENT_TRUSTED_OPTION_DATA",
        "reason": "No trusted executable option bid/ask replay ledger with entry ask, exit bid, and costs exists for the frozen ORB candidate universe.",
        "pr_682_state": "OPEN",
        "pr_682_draft": "YES",
        "pr_682_merged": "NO",
        "validated_production_source_sha": CORRECTED_SHA,
        "research_execution_head": source_identity["research_execution_head"],
        "research_branch": source_identity["research_branch"],
        "contract_hash": contract_hash,
        "dataset_manifest_hash": manifest_hash,
        "trusted_option_bid_ask_available": "NO",
        "candidate_conservation": conservation["decision"],
        "base_candidate_count": None,
        "corrected_candidate_count": len(candidates),
        "current_certified_candidate_count": len(candidates),
        "non_score_candidate_differences": None,
        "underlying_outcome_invariance": "NOT_EVALUATED",
        "option_economic_outcome_invariance": "NOT_EVALUABLE_NO_TRUSTED_OPTION_DATA",
        "all_candidate_net_expectancy": None,
        "historical_top_20_net_expectancy": None,
        "corrected_top_20_net_expectancy": None,
        "corrected_top_minus_bottom_spread": None,
        "corrected_versus_historical_lift": None,
        "development_folds": [],
        "final_holdout": None,
        "session_cluster_confidence_intervals": None,
        "profit_factor": None,
        "maximum_drawdown": None,
        "call_results": {"candidate_count": directions.get("BUY_CALL", 0)},
        "put_results": {"candidate_count": directions.get("BUY_PUT", 0)},
        "session_concentration": {"session_count": len(sessions), "cannot_calculate_net_pnl_concentration": True},
        "negative_controls": "not run for option economics; missing executable option outcomes",
        "determinism": "PENDING_TWO_RUN_COMPARISON" if determinism_hash == "PENDING" else "PASS",
        "determinism_hash": determinism_hash,
        "underlying_signal": "UNDERLYING_SIGNAL_EVALUATION_INCOMPLETE",
        "option_economic_edge": "INSUFFICIENT_TRUSTED_OPTION_DATA",
        "production_files_changed": "NO",
        "thresholds_changed": "NO",
        "parameters_tuned": "NO",
        "broker_api_called": "NO",
        "order_action": "NO",
        "pushed": "NO",
        "new_pr_created": "NO",
        "next_action": "Acquire or certify a historical option bid/ask replay ledger for the exact 2215 ORB candidate universe before making any option-edge claim.",
    }


def build_report(final_verdict: dict[str, Any], contract_hash: str, manifest_hash: str) -> str:
    return f"""# ORB Corrected Score Structural-Edge Revalidation

FINAL VERDICT: {final_verdict["final_verdict"]}

The corrected PR #682 ORB score repair was evaluated as an offline research question against validated production source `{CORRECTED_SHA}` from research execution head `{final_verdict["research_execution_head"]}`. The existing ORB candidate and outcome artifacts are sufficient for candidate identity inventory and underlying descriptive outcomes, but not for executable option economics.

## Evidence Boundary

- Contract hash: `{contract_hash}`
- Dataset manifest hash: `{manifest_hash}`
- Current certified candidate count: {final_verdict["current_certified_candidate_count"]}
- Candidate conservation: {final_verdict["candidate_conservation"]}
- Trusted option bid/ask available: NO
- Production files changed: NO
- Thresholds changed: NO
- Parameters tuned: NO
- Broker API called: NO
- Order action: NO

## Decision

No structural option edge is claimed. Existing certified ORB outcome artifacts are explicitly descriptive, pre-cost, underlying-only evidence. Candidate conservation is not claimed because a genuine baseline-versus-corrected dual replay was not executed. The required entry ask, exit bid, cost, and option trade ledger authority is absent for the frozen candidate universe. Underlying signal evaluation is also incomplete because this task did not compute and audit chronological folds, holdout results, session-cluster uncertainty, negative controls, and concentration analysis.

Parquet ledgers are not generated when authoritative inputs are unavailable. Missing ledgers are recorded as unavailable metadata in `external_artifact_manifest.json`; zero-byte placeholder Parquet files are invalid evidence.

## Next Action

{final_verdict["next_action"]}
"""


def generate_compact(output_dir: Path = OUTPUT_DIR, determinism_hash: str = "PENDING") -> dict[str, Any]:
    source_identity = verify_source_identity()
    contract = build_contract()
    contract_hash = write_json(output_dir / "edge_validation_contract.json", contract)
    manifest = build_dataset_manifest(contract_hash)
    manifest_hash = write_json(output_dir / "dataset_manifest.json", manifest)
    artifacts: dict[str, dict[str, Any]] = {
        "source_identity.json": source_identity,
        "candidate_conservation.json": build_candidate_conservation(),
        "candidate_semantic_hashes.json": {
            "schema_version": 1,
            "candidate_semantic_hash": build_candidate_conservation()["candidate_semantic_hash"],
            "candidate_count": len(candidate_records()),
            **safety_fields(),
        },
        "outcome_invariance.json": build_outcome_invariance(),
        "underlying_outcome_summary.json": build_underlying_summary(),
        "option_economic_summary.json": build_empty_gate_artifact("OPTION_ECONOMIC_SUMMARY", "INSUFFICIENT_TRUSTED_OPTION_DATA", "No trusted option bid/ask ledger is available."),
        "score_discrimination_summary.json": build_score_summary(),
        "wfa_fold_results.json": build_empty_gate_artifact("WFA_FOLD_RESULTS", "BLOCKED_BY_MISSING_TRUSTED_OPTION_DATA", "Walk-forward option economics require executable option outcomes."),
        "holdout_results.json": build_empty_gate_artifact("HOLDOUT_RESULTS", "BLOCKED_BY_MISSING_TRUSTED_OPTION_DATA", "Holdout option economics require executable option outcomes."),
        "statistical_uncertainty.json": build_empty_gate_artifact("STATISTICAL_UNCERTAINTY", "BLOCKED_BY_MISSING_TRUSTED_OPTION_DATA", "Session-clustered option PnL intervals require executable option outcomes."),
        "negative_controls.json": build_empty_gate_artifact("NEGATIVE_CONTROLS", "BLOCKED_BY_MISSING_TRUSTED_OPTION_DATA", "Economic score controls require executable option outcomes."),
        "concentration_analysis.json": build_empty_gate_artifact("CONCENTRATION_ANALYSIS", "BLOCKED_BY_MISSING_TRUSTED_OPTION_DATA", "Net PnL concentration requires executable option outcomes."),
        "external_artifact_manifest.json": build_external_artifact_manifest(),
    }
    for name, payload in artifacts.items():
        write_json(output_dir / name, payload)
    for stale in ("old_vs_corrected_score_ledger.parquet", "option_trade_ledger.parquet"):
        stale_path = output_dir / stale
        if stale_path.exists():
            stale_path.unlink()
    write_text(output_dir / "candidate_conservation.md", "# Candidate Conservation\n\nNOT_EVALUATED_DUAL_REPLAY_UNAVAILABLE. No baseline candidate count is inferred from the corrected ledger.")
    write_text(output_dir / "outcome_invariance.md", "# Outcome Invariance\n\nExecutable option outcome invariance is blocked: the available ORB v2 outcome ledger is underlying-only and pre-cost.")
    final_verdict = build_final_verdict(contract_hash, manifest_hash, determinism_hash, source_identity)
    write_json(output_dir / "final_verdict.json", final_verdict)
    write_text(output_dir / "final_report.md", build_report(final_verdict, contract_hash, manifest_hash))
    return {"contract_hash": contract_hash, "dataset_manifest_hash": manifest_hash, "final_verdict": final_verdict}


def generate(output_dir: Path = OUTPUT_DIR, *, skip_determinism: bool = False) -> dict[str, Any]:
    if skip_determinism:
        return generate_compact(output_dir, determinism_hash="PENDING")
    run_a = Path("/tmp/orb-corrected-score-run-a")
    run_b = Path("/tmp/orb-corrected-score-run-b")
    for path in (run_a, run_b):
        if path.exists():
            shutil.rmtree(path)
        generate_compact(path, determinism_hash="PENDING")
    determinism = compare_outputs(run_a, run_b)
    if determinism["decision"] != "PASS":
        raise RuntimeError(f"DETERMINISM_FAILED {json.dumps(determinism, sort_keys=True)}")
    result = generate_compact(output_dir, determinism_hash=determinism["determinism_hash"])
    write_json(output_dir / "determinism_report.json", determinism)
    write_text(output_dir / "determinism_report.md", "# Determinism\n\nPASS after independent two-directory compact artifact comparison. Unavailable ledgers are recorded as NOT_APPLICABLE_ARTIFACT_UNAVAILABLE.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--skip-determinism", action="store_true")
    args = parser.parse_args()
    result = generate(args.output_dir, skip_determinism=args.skip_determinism)
    print(result["final_verdict"]["final_verdict"])
    print(f"contract_hash={result['contract_hash']}")
    print(f"dataset_manifest_hash={result['dataset_manifest_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
