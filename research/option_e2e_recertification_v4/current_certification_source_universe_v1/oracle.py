from __future__ import annotations

from typing import Any


def recompute_legacy_disposition(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records", [])
    unresolved = sum(1 for item in records if item.get("confidence") == "UNRESOLVED")
    exact = sum(1 for item in records if item.get("exact_prior_path"))
    verdict = (
        "LEGACY_27_ROOT_CENSUS_REPRODUCIBLE"
        if len(records) == 27 and exact == 27
        else "LEGACY_27_ROOT_CENSUS_NON_REPRODUCIBLE_MISSING_PATH_BINDINGS"
    )
    return {
        "schema_version": "legacy_27_root_reconstruction_oracle_v1",
        "prior_root_count": len(records),
        "exact_paths_recovered": exact,
        "unresolved_roots": unresolved,
        "primary_verdict": payload.get("verdict"),
        "oracle_verdict": verdict,
        "primary_oracle_agreement": "AGREEMENT" if payload.get("verdict") == verdict else "DISAGREEMENT",
    }


def recompute_current_universe(machine: dict[str, Any], portable: dict[str, Any]) -> dict[str, Any]:
    machine_ids = [root.get("current_root_id") for root in machine.get("roots", [])]
    portable_ids = [root.get("current_root_id") for root in portable.get("roots", [])]
    absolute_paths_in_portable = "Users/madhuram" in str(portable)
    agreement = machine_ids == portable_ids and not absolute_paths_in_portable
    return {
        "schema_version": "current_certification_source_universe_oracle_v1",
        "root_count": len(machine_ids),
        "machine_root_ids": machine_ids,
        "portable_root_ids": portable_ids,
        "absolute_paths_in_portable": absolute_paths_in_portable,
        "primary_oracle_agreement": "AGREEMENT" if agreement else "DISAGREEMENT",
        "verdict": "CURRENT_CERTIFICATION_SOURCE_UNIVERSE_FROZEN" if agreement else "INVALID_CURRENT_SOURCE_UNIVERSE",
    }
