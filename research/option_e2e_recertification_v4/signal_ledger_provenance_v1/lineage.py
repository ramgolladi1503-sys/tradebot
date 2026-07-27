from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .git_provenance import (
    EXPECTED_INTRODUCTION_COMMIT,
    GENERATOR_RELATIVE_PATH,
    INVENTORY_RELATIVE_PATH,
    LEDGER_RELATIVE_PATH,
    SIDECAR_RELATIVE_PATH,
    ProvenanceError,
    discover_path_history,
    execute_historical_generator,
    git_blob_sha,
    git_object_bytes,
    path_exists,
    reconstruct_historical_generator_output,
    run_git,
    sha256_bytes,
)


def discover_introduction_history(repo_root: Path, paths: Sequence[str]) -> dict[str, Any]:
    records = {path: discover_path_history(repo_root, path) for path in paths}
    ledger_commit = records[LEDGER_RELATIVE_PATH]["first_add_commit"]
    sidecar_commit = records[SIDECAR_RELATIVE_PATH]["first_add_commit"]
    introduction_commit = ledger_commit if ledger_commit == sidecar_commit else None
    support_present = bool(
        introduction_commit
        and path_exists(repo_root, introduction_commit, GENERATOR_RELATIVE_PATH)
        and path_exists(repo_root, introduction_commit, INVENTORY_RELATIVE_PATH)
    )
    if introduction_commit is None or not support_present:
        status = "UNRESOLVED"
    else:
        prior_lineage = any(
            records[path]["first_add_commit"] != introduction_commit
            for path in (GENERATOR_RELATIVE_PATH, INVENTORY_RELATIVE_PATH)
        )
        status = "PROVEN_WITH_PRIOR_LINEAGE" if prior_lineage else "PROVEN"
    return {
        "atomic_introduction_status": status,
        "introduction_commit": introduction_commit,
        "paths": records,
        "generator_and_inventory_present_at_introduction": support_present,
        "configured_expected_commit": EXPECTED_INTRODUCTION_COMMIT,
        "configured_commit_matches_discovery": introduction_commit == EXPECTED_INTRODUCTION_COMMIT,
    }


def build_historical_binding(
    repo_root: Path,
    expected_introduction_commit: str | None = EXPECTED_INTRODUCTION_COMMIT,
) -> dict[str, Any]:
    paths = [LEDGER_RELATIVE_PATH, SIDECAR_RELATIVE_PATH, GENERATOR_RELATIVE_PATH, INVENTORY_RELATIVE_PATH]
    history = discover_introduction_history(repo_root, paths)
    introduction_commit = history["introduction_commit"]
    if introduction_commit is None or history["atomic_introduction_status"] == "UNRESOLVED":
        raise ProvenanceError("ATOMIC_INTRODUCTION_UNRESOLVED")
    if expected_introduction_commit is not None and introduction_commit != expected_introduction_commit:
        raise ProvenanceError("INTRODUCTION_COMMIT_MISMATCH")

    historical_ledger = git_object_bytes(repo_root, f"{introduction_commit}:{LEDGER_RELATIVE_PATH}")
    historical_sidecar = git_object_bytes(repo_root, f"{introduction_commit}:{SIDECAR_RELATIVE_PATH}")
    historical_generator = git_object_bytes(repo_root, f"{introduction_commit}:{GENERATOR_RELATIVE_PATH}")
    historical_inventory = git_object_bytes(repo_root, f"{introduction_commit}:{INVENTORY_RELATIVE_PATH}")
    current_ledger = (repo_root / LEDGER_RELATIVE_PATH).read_bytes()
    current_generator = (repo_root / GENERATOR_RELATIVE_PATH).read_bytes()
    primary = execute_historical_generator(historical_generator, historical_inventory)
    oracle = reconstruct_historical_generator_output(historical_generator, historical_inventory)
    historical_sha = sha256_bytes(historical_ledger)
    sidecar_token = historical_sidecar.decode("utf-8").strip().split()[0]
    binding_proven = historical_ledger == primary == oracle

    return {
        "history": history,
        "historical_blobs": {
            "ledger_git_blob_sha": git_blob_sha(repo_root, introduction_commit, LEDGER_RELATIVE_PATH),
            "sidecar_git_blob_sha": git_blob_sha(repo_root, introduction_commit, SIDECAR_RELATIVE_PATH),
            "generator_git_blob_sha": git_blob_sha(repo_root, introduction_commit, GENERATOR_RELATIVE_PATH),
            "inventory_git_blob_sha": git_blob_sha(repo_root, introduction_commit, INVENTORY_RELATIVE_PATH),
            "historical_ledger_physical_sha256": historical_sha,
            "historical_generator_content_sha256": sha256_bytes(historical_generator),
            "current_ledger_git_blob_sha": str(run_git(repo_root, "rev-parse", f"HEAD:{LEDGER_RELATIVE_PATH}")).strip(),
            "current_generator_git_blob_sha": str(run_git(repo_root, "rev-parse", f"HEAD:{GENERATOR_RELATIVE_PATH}")).strip(),
            "current_ledger_physical_sha256": sha256_bytes(current_ledger),
            "current_generator_content_sha256": sha256_bytes(current_generator),
            "historical_current_ledger_equality": historical_ledger == current_ledger,
            "historical_current_generator_equality": historical_generator == current_generator,
            "historical_sidecar_matches_ledger": sidecar_token == historical_sha,
        },
        "generator_output_binding": {
            "status": "PROVEN" if binding_proven else "CONFLICTING",
            "historical_committed_sha256": historical_sha,
            "primary_regenerated_sha256": sha256_bytes(primary),
            "independent_reconstruction_sha256": sha256_bytes(oracle),
            "byte_equality": binding_proven,
            "semantic_equality": json.loads(historical_ledger) == json.loads(primary) == json.loads(oracle),
        },
        "historical_inventory": json.loads(historical_inventory),
    }
