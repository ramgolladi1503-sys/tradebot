#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.opening_range_retest_v2.recertification import (  # noqa: E402
    V2Artifacts,
    build_v2_artifacts,
    canonical_json_bytes,
    sha256_bytes,
    verify_artifact_sidecars,
    write_artifacts,
)


def _git_head() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def _determinism_projection(artifacts: V2Artifacts) -> dict[str, object]:
    def stable(payload: object) -> object:
        if isinstance(payload, dict):
            return {
                key: stable(value)
                for key, value in payload.items()
                if key not in {"timestamp", "diagnostic_absolute_path"}
            }
        if isinstance(payload, list):
            return [stable(value) for value in payload]
        return payload

    source_record_ids = [record["source_record_id"] for record in artifacts.source_manifest["records"]]
    candidate_ids = [record["candidate_id"] for record in artifacts.candidate_ledger["records"]]
    return {
        "source_manifest_payload_hash": sha256_bytes(canonical_json_bytes(stable(artifacts.source_manifest))),
        "source_manifest_semantic_hash": artifacts.source_manifest["source_manifest_semantic_hash"],
        "source_record_count": artifacts.source_manifest["record_count"],
        "source_record_ids_hash": sha256_bytes(canonical_json_bytes(source_record_ids)),
        "candidate_ledger_payload_hash": sha256_bytes(canonical_json_bytes(stable(artifacts.candidate_ledger))),
        "candidate_count": artifacts.candidate_ledger["candidate_count"],
        "candidate_ids_hash": sha256_bytes(canonical_json_bytes(candidate_ids)),
        "candidate_core_semantic_hash": artifacts.candidate_ledger["candidate_core_semantic_hash"],
        "candidate_provenance_semantic_hash": artifacts.candidate_ledger["candidate_provenance_semantic_hash"],
        "source_oracle_verdict": artifacts.source_oracle["verdict"],
        "candidate_oracle_verdict": artifacts.candidate_oracle["verdict"],
        "summary_payload_hash": sha256_bytes(canonical_json_bytes(stable(artifacts.summary))),
        "summary_decision": artifacts.summary["decision"],
        "reconciliation_payload_hash": sha256_bytes(canonical_json_bytes(stable(artifacts.reconciliation))),
        "reconciliation_decision": artifacts.reconciliation["decision"],
        "reconciliation_projection_hashes": {
            "v1": artifacts.reconciliation.get("v1_common_projection_hash"),
            "v2": artifacts.reconciliation.get("v2_common_projection_hash"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ORB Phase 1 v2 source-provenance recertification.")
    parser.add_argument("--base-main-sha", required=True)
    parser.add_argument("--source-project-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "docs" / "agent_reviews")
    parser.add_argument("--determinism-dir-a", type=Path, default=PROJECT_ROOT / ".runtime" / "orb_phase1_v2_determinism_a")
    parser.add_argument("--determinism-dir-b", type=Path, default=PROJECT_ROOT / ".runtime" / "orb_phase1_v2_determinism_b")
    parser.add_argument("--max-workers", type=int, default=8)
    args = parser.parse_args()

    execution_commit_sha = _git_head()
    shutil.rmtree(args.determinism_dir_a, ignore_errors=True)
    shutil.rmtree(args.determinism_dir_b, ignore_errors=True)
    artifacts_a = build_v2_artifacts(
        base_main_sha=args.base_main_sha,
        execution_commit_sha=execution_commit_sha,
        max_workers=args.max_workers,
        source_project_root=args.source_project_root,
    )
    write_artifacts(artifacts_a, args.determinism_dir_a)
    artifacts_b = build_v2_artifacts(
        base_main_sha=args.base_main_sha,
        execution_commit_sha=execution_commit_sha,
        max_workers=args.max_workers,
        source_project_root=args.source_project_root,
    )
    write_artifacts(artifacts_b, args.determinism_dir_b)
    projection_a = _determinism_projection(artifacts_a)
    projection_b = _determinism_projection(artifacts_b)
    if projection_a != projection_b:
        print(json.dumps({"verdict": "TWO_DIRECTORY_DETERMINISM_FAIL", "run_a": projection_a, "run_b": projection_b}, sort_keys=True))
        return 2
    paths = write_artifacts(artifacts_a, args.output_dir)
    sidecars = verify_artifact_sidecars(paths)
    print(
        json.dumps(
            {
                "verdict": artifacts_a.summary["decision"],
                "source_verdict": artifacts_a.source_oracle["verdict"],
                "source_authority_root": artifacts_a.source_oracle.get("source_authority_root"),
                "candidate_verdict": artifacts_a.candidate_oracle["verdict"],
                "two_directory_verdict": "TWO_DIRECTORY_DETERMINISM_PASS",
                "sidecar_verdict": sidecars["verdict"],
                "sidecars": sidecars,
                "projection": projection_a,
                "paths": paths,
            },
            sort_keys=True,
        )
    )
    return 0 if artifacts_a.summary["decision"] == "ORB_PHASE1_V2_RECERTIFIED" and sidecars["verdict"] == "ARTIFACT_SIDECARS_CERTIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
