from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import envelope, write_json
from .contracts import canonical_hash


def candidate_bundle(
    *,
    candidate: dict[str, Any],
    side: str,
    source_manifest_hash: str,
    development_dataset_hash: str,
    feature_schema_hash: str,
    fold_manifest_hash: str,
    search_space_hash: str,
    multiple_testing: dict[str, Any],
    recurrence: dict[str, Any],
    concentration: dict[str, Any],
    bootstrap: dict[str, Any],
    imputation_dependence: dict[str, Any],
    controls: dict[str, Any],
    code_sha: str,
) -> dict[str, Any]:
    if side not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")
    economic = {
        "side": side,
        "candidate": candidate,
        "source_manifest_hash": source_manifest_hash,
        "development_dataset_hash": development_dataset_hash,
        "feature_schema_hash": feature_schema_hash,
        "fold_manifest_hash": fold_manifest_hash,
        "search_space_hash": search_space_hash,
        "multiple_testing": multiple_testing,
        "recurrence": recurrence,
        "concentration": concentration,
        "bootstrap": bootstrap,
        "imputation_dependence": imputation_dependence,
        "controls": controls,
        "code_commit_sha": code_sha,
    }
    bundle_hash = canonical_hash(economic)
    return {
        **economic,
        "candidate_id": f"v2_{side.lower()}_{bundle_hash[:16]}",
        "candidate_bundle_hash": bundle_hash,
        "status": "FRESH_CONFIRMATION_REQUIRES_EXPLICIT_ACKNOWLEDGEMENT",
    }


def write_frozen_registry(
    output_path: str | Path,
    *,
    bundles: list[dict[str, Any]],
    code_sha: str,
    input_hashes: dict[str, str],
    seeds: list[int],
) -> dict[str, Any]:
    seen_sides: set[str] = set()
    for bundle in bundles:
        side = str(bundle["side"])
        if side in seen_sides:
            raise ValueError(f"at most one frozen candidate per side: {side}")
        seen_sides.add(side)
    payload = envelope(
        {
            "verdict": (
                "NO_STABLE_CANDIDATE"
                if not bundles
                else "ONE_CANDIDATE_PER_SIDE_FROZEN"
                if len(bundles) == 2
                else f"ONE_{bundles[0]['side']}_V2_CANDIDATE_FROZEN"
            ),
            "candidates": bundles,
            "confirmation_token_issued": False,
        },
        code_sha=code_sha,
        input_hashes=input_hashes,
        deterministic_seeds=seeds,
    )
    write_json(output_path, payload)
    return payload
