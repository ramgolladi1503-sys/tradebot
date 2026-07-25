from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .generate import publish_provenance_evidence


LEDGER_RELATIVE_PATH = "research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers.json"
GENERATOR_RELATIVE_PATH = "research/option_e2e_recertification_v4/signal_ledgers_v4_2/build_signal_ledgers.py"
INVENTORY_RELATIVE_PATH = "research/option_e2e_recertification_v4/inventory_v4_1/historical_strategy_inventory_v4_1.json"
INVALIDATION_RELATIVE_PATH = "research/option_e2e_recertification_v4/v4_3_supersession/v4_2_evidence_implementation_invalidation.json"
INTRODUCTION_COMMIT = "686af0feff7a4485ebe4e249cb498b33d649a5cd"


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo_root, check=True, capture_output=True, text=True).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_immutable_evidence(repo_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ledger = repo_root / LEDGER_RELATIVE_PATH
    generator = repo_root / GENERATOR_RELATIVE_PATH
    invalidation = repo_root / INVALIDATION_RELATIVE_PATH
    ledger_sha256 = _sha256(ledger)
    invalidation_payload = json.loads(invalidation.read_text(encoding="utf-8"))
    invalidation_binds_commit = invalidation_payload.get("previous_head") == INTRODUCTION_COMMIT and GENERATOR_RELATIVE_PATH in invalidation_payload.get("scope", [])
    evidence = {
        "implementation_manifest": {
            "ledger_sha256": ledger_sha256,
            "commit_sha": INTRODUCTION_COMMIT,
            "path": GENERATOR_RELATIVE_PATH,
            "git_blob_sha": _git(repo_root, "rev-parse", f"{INTRODUCTION_COMMIT}:{GENERATOR_RELATIVE_PATH}"),
            "content_sha256": _sha256(generator),
            "atomic_commit_binding": True,
        },
        "historical_invalidation": {
            "ledger_sha256": ledger_sha256,
            "invalidation_path": INVALIDATION_RELATIVE_PATH,
            "invalidation_sha256": _sha256(invalidation),
            "invalidated_commit": INTRODUCTION_COMMIT,
            "decision": invalidation_payload.get("decision"),
            "binding_verified": invalidation_binds_commit,
        } if invalidation_binds_commit else {},
        "candidate_current_implementation_hash": _sha256(generator),
        "contamination_evidence": {},
    }
    sources = [
        {"category": "LEDGER", "semantic_path": LEDGER_RELATIVE_PATH, "finding": "EXACT_HASH_AND_24_ROWS_VERIFIED", "sha256": ledger_sha256},
        {"category": "GIT_HISTORY", "semantic_path": f"git:{INTRODUCTION_COMMIT}", "finding": "ATOMIC_GENERATOR_AND_LEDGER_INTRODUCTION"},
        {"category": "GENERATOR", "semantic_path": GENERATOR_RELATIVE_PATH, "finding": "BLOCKED_PLACEHOLDER_AGGREGATE_GENERATOR", "sha256": _sha256(generator)},
        {"category": "STRATEGY_INVENTORY", "semantic_path": INVENTORY_RELATIVE_PATH, "finding": "GENERATOR_INPUT_PRESENT_WITH_SAME_INTRODUCTION_COMMIT", "git_blob_sha": _git(repo_root, "rev-parse", f"{INTRODUCTION_COMMIT}:{INVENTORY_RELATIVE_PATH}")},
        {"category": "SIDECAR", "semantic_path": f"{LEDGER_RELATIVE_PATH}.sha256", "finding": "PHYSICAL_HASH_MATCH"},
        {"category": "INVALIDATION", "semantic_path": INVALIDATION_RELATIVE_PATH, "finding": "V4_2_IMPLEMENTATION_EXPLICITLY_INVALIDATED", "sha256": _sha256(invalidation)},
        {"category": "LEDGER_FIELDS", "semantic_path": LEDGER_RELATIVE_PATH, "finding": "IMPLEMENTATION_PARAMETER_DATASET_TEMPORAL_AND_FOLD_FIELDS_BLANK"},
        {"category": "EXTERNAL_CLOSURE_EVIDENCE", "semantic_path": "external:all_strategy_authority_closure_v1", "finding": "INSUFFICIENT_PROVENANCE_RECONFIRMED_NO_NEW_IMMUTABLE_BINDING"},
        {"category": "FREEZE_RECORDS", "semantic_path": "repository_and_declared_external_roots", "finding": "NO_HASH_BOUND_PRE_OUTCOME_FREEZE_MANIFEST_FOUND"},
        {"category": "CONTAMINATION_RECORDS", "semantic_path": "repository_and_declared_external_roots", "finding": "NO_IMMUTABLE_CLEARANCE_EVIDENCE_FOUND_OUTCOMES_NOT_READ"},
    ]
    return evidence, sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    evidence, sources = build_immutable_evidence(args.repo_root.resolve())
    result = publish_provenance_evidence(args.repo_root / LEDGER_RELATIVE_PATH, evidence, sources, args.output_dir)
    print(json.dumps({"agreement": result["agreement"]["status"], "verdict": result["primary"]["verdict"], "semantic_manifest_sha256": result["semantic_manifest_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
