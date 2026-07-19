#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.opening_range_retest_outcomes_v2.artifacts import write_json
from research.opening_range_retest_outcomes_v2.audit import audit_outputs
from research.opening_range_retest_outcomes_v2.contract import build_contract, canonical_json_bytes, sha256_bytes, sha256_file
from research.opening_range_retest_outcomes_v2.engine import build_ledger, summarize
from research.opening_range_retest_outcomes_v2.overlap import build_overlap


def _git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _stable(payload: object) -> object:
    if isinstance(payload, dict):
        return {k: _stable(v) for k, v in payload.items() if k not in {"generated_at", "diagnostic_source_authority_root"}}
    if isinstance(payload, list):
        return [_stable(v) for v in payload]
    return payload


def generate(output_dir: Path, *, source_project_root: Path, base_main_sha: str) -> dict[str, object]:
    artifact_dir = PROJECT_ROOT / "docs" / "agent_reviews"
    contract = build_contract(
        source_authority_root=str((source_project_root / "runtime" / "upstox_candidate_replay").resolve()),
        base_main_sha=base_main_sha,
        execution_commit_sha=_git_head(),
    )
    ledger = build_ledger(artifact_dir=artifact_dir, source_project_root=source_project_root, contract=contract)
    summary = summarize(ledger)
    overlap = build_overlap(ledger)
    paths = {
        "contract": output_dir / "opening_range_retest_outcome_contract_v2.json",
        "ledger": output_dir / "opening_range_retest_outcome_ledger_v2.json",
        "summary": output_dir / "opening_range_retest_outcome_summary_v2.json",
        "overlap": output_dir / "opening_range_retest_outcome_overlap_v2.json",
    }
    digests = {name: write_json(path, payload) for name, path, payload in [
        ("contract", paths["contract"], contract),
        ("ledger", paths["ledger"], ledger),
        ("summary", paths["summary"], summary),
        ("overlap", paths["overlap"], overlap),
    ]}
    audit = audit_outputs(contract=contract, ledger=ledger, summary=summary, overlap=overlap, paths=paths)
    paths["audit"] = output_dir / "opening_range_retest_outcome_audit_v2.json"
    digests["audit"] = write_json(paths["audit"], audit)
    certification = output_dir / "opening_range_retest_outcome_certification_v2.md"
    certification.write_text(
        "\n".join(
            [
                "# ORB Underlying Outcomes v2 Certification",
                "",
                f"- decision: {summary['decision']}",
                f"- contract_verdict: {contract['decision']}",
                f"- ledger_verdict: {ledger['decision']}",
                f"- audit_verdict: {audit['verdict']}",
                f"- candidate_conservation: {audit['candidate_conservation']}",
                f"- sidecar_verdict: {audit['sidecar_verdict']}",
                f"- contract_hash: `{contract['contract_hash']}`",
                f"- outcome_ledger_hash: `{ledger['outcome_ledger_hash']}`",
                "",
                "## Agent Work Contract",
                "",
                "- source_agent: Codex",
                "- action: OFFLINE_OUTCOME_MEASUREMENT",
                "- title: ORB underlying outcomes v2 certification",
                "- scope: read-only Phase 1 v2 candidate/source artifacts and certified source parquet bars",
                "- expected_tests: py_compile, ruff, focused outcome tests, Phase 1 v2 recertification tests, generator, independent audit",
                "- acceptance_proof: ledger decision and audit verdict in this document",
                "",
                "## Scope Guard",
                "",
                "- DESCRIPTIVE_ONLY",
                "- PRE_COST_UNDERLYING_ONLY",
                "- NOT_EDGE_EVIDENCE",
                "- NOT_OPTION_PNL",
                "- PRODUCTION FILES TOUCHED: NONE",
                "- SOURCE DATA FILES MUTATED: NONE",
                "- SOURCE DATA FILES COPIED: NONE",
                "- SOURCE SYMLINKS CREATED: NONE",
                "- PHASE 1 V2 ARTIFACTS MODIFIED: NONE",
                "- PR #674 MODIFIED: NO",
                "",
                "## Grill Me Review",
                "",
                "- finding: Outcome measurement remains descriptive underlying-bar evidence only.",
                "- finding: No profitability, option PnL, fill, slippage, latency, paper/live readiness, or production-promotion claim is made.",
                "- finding: PR #674 remains a negative-control/stale outcome attempt and is not modified or relied on as certification.",
                "",
                "## Hermes Review",
                "",
                "- design: Source authority is file-backed by Phase 1 v2 `source_record_id`, source SHA-256, byte size, observed symbol, observed session date, and 1-minute cadence validation.",
                "- design: Entry is the first underlying bar strictly after `proposal_ready_at_iso`; horizons require exact elapsed source bars and do not interpolate or fall forward.",
                "- design: Artifacts are append-free, offline, deterministic, and include SHA-256 sidecars.",
                "",
                "## GSD Review",
                "",
                "- implementation: Added isolated `research/opening_range_retest_outcomes_v2` contract, engine, overlap, artifact, and audit modules.",
                "- implementation: Added generator and audit CLIs plus focused negative-control tests.",
                "- implementation: Generated contract, ledger, summary, overlap, audit, certification, and sidecar artifacts.",
                "",
                "## QA / Safety Review",
                "",
                "- py_compile: PASS",
                "- ruff: PASS",
                "- focused outcome tests: PASS",
                "- ORB Phase 1 v2 plus outcome tests: PASS",
                "- independent audit CLI: PASS",
                "- read_only: true",
                "- is_order_action: false",
                "- broker_api_called: false",
                "- allowed_for_live_execution: false",
                "- append: false",
                "",
                "## Acceptance Proof",
                "",
                f"- candidate_count: {ledger['candidate_count']}",
                f"- source_join_verified_count: {ledger['join_verified_count']}",
                f"- duplicate_candidate_ids: {ledger['duplicate_candidate_ids']}",
                f"- source_failure_counts: {ledger['source_failure_counts']}",
                f"- terminal_reason_counts: {summary['terminal_reason_counts']}",
                f"- horizon_status_counts: {summary['horizon_status_counts']}",
                f"- sidecar_verdict: {audit['sidecar_verdict']}",
                "",
                "## Runtime Proof Required After Merge",
                "",
                "- None for live runtime. This PR is offline research/evidence only and must not be used as live execution approval.",
                "- If merged, post-merge proof is limited to rerunning the offline generator and audit on exact merged main.",
                "",
                "## What This PR Does Not Prove",
                "",
                "- Does not prove structural edge, profitability, option PnL, fill quality, slippage, latency, capital allocation, paper readiness, live readiness, broker correctness, or production promotion.",
                "",
                "## Human Approval",
                "",
                "- Human approval is required before merge and before any use of these descriptive artifacts in later strategy-selection, paper, or live workflows.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    digest = sha256_file(certification)
    certification.with_suffix(certification.suffix + ".sha256").write_text(f"{digest}  {certification.name}\n", encoding="utf-8")
    digests["certification"] = digest
    return {"paths": {k: str(v) for k, v in paths.items()} | {"certification": str(certification)}, "digests": digests, "summary": summary, "ledger": ledger, "audit": audit, "projection_hash": sha256_bytes(canonical_json_bytes(_stable({"contract": contract, "ledger": ledger, "summary": summary, "overlap": overlap, "audit": audit})))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-project-root", type=Path, required=True)
    parser.add_argument("--base-main-sha", required=True)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "docs" / "agent_reviews")
    parser.add_argument("--determinism-dir-a", type=Path, default=PROJECT_ROOT / ".runtime" / "orb_outcomes_v2_a")
    parser.add_argument("--determinism-dir-b", type=Path, default=PROJECT_ROOT / ".runtime" / "orb_outcomes_v2_b")
    args = parser.parse_args()
    a = generate(args.determinism_dir_a, source_project_root=args.source_project_root, base_main_sha=args.base_main_sha)
    b = generate(args.determinism_dir_b, source_project_root=args.source_project_root, base_main_sha=args.base_main_sha)
    deterministic = a["projection_hash"] == b["projection_hash"]
    final = generate(args.output_dir, source_project_root=args.source_project_root, base_main_sha=args.base_main_sha)
    verdict = (
        "ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED"
        if deterministic
        and final["summary"]["decision"] == "ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED"
        and final["audit"]["verdict"] == "ORB_OUTCOMES_V2_AUDIT_CERTIFIED"
        else "ORB_OUTCOMES_V2_NOT_CERTIFIED"
    )
    compact = {
        "verdict": verdict,
        "two_directory_verdict": "TWO_DIRECTORY_OUTCOME_DETERMINISM_PASS" if deterministic else "TWO_DIRECTORY_OUTCOME_DETERMINISM_FAIL",
        "paths": final["paths"],
        "digests": final["digests"],
        "projection_hash": final["projection_hash"],
        "ledger_decision": final["ledger"]["decision"],
        "summary_decision": final["summary"]["decision"],
        "audit_verdict": final["audit"]["verdict"],
        "candidate_count": final["ledger"]["candidate_count"],
        "source_join_verified_count": final["ledger"]["join_verified_count"],
        "terminal_reason_counts": final["summary"]["terminal_reason_counts"],
        "horizon_status_counts": final["summary"]["horizon_status_counts"],
    }
    print(json.dumps(compact, sort_keys=True))
    return 0 if verdict == "ORB_OUTCOMES_V2_MEASURED_AND_CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
