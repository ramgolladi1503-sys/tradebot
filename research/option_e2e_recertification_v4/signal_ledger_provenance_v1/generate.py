from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .audit import EXPECTED_LEDGER_SHA256, EXPECTED_ROW_COUNT, SAFETY_FLAGS, audit_signal_ledger, semantic_sha256
from .git_provenance import LEDGER_RELATIVE_PATH
from .oracle import oracle_audit

OUTPUT_NAMES = (
    "schema.json",
    "signal_ledger_source_inventory.json",
    "signal_ledger_ownership_review.json",
    "signal_ledger_implementation_review.json",
    "signal_ledger_parameter_review.json",
    "signal_ledger_dataset_review.json",
    "signal_ledger_temporal_split_review.json",
    "signal_ledger_freeze_contamination_review.json",
    "signal_ledger_provenance_summary.json",
    "external_evidence_manifest.json",
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.write_text(content, encoding="utf-8")
    path.with_suffix(path.suffix + ".sha256").write_text(f"{hashlib.sha256(content.encode()).hexdigest()}  {path.name}\n", encoding="utf-8")


def _agreement(primary: Mapping[str, Any], oracle: Mapping[str, Any]) -> dict[str, Any]:
    history = primary["implementation"]["historical_binding"]["history"]
    blobs = primary["implementation"]["historical_binding"]["historical_blobs"]
    generator_binding = primary["implementation"]["historical_binding"]["generator_output_binding"]
    invalidation = primary["historical_invalidation"]
    checks = {
        "physical_hash": oracle.get("physical_hash_matches") is True and primary["ledger"]["physical_sha256"] == EXPECTED_LEDGER_SHA256,
        "row_count": oracle.get("row_count_matches") is True and primary["ledger"]["row_count"] == EXPECTED_ROW_COUNT,
        "introduction_commit": history.get("introduction_commit") == oracle.get("introduction_commit"),
        "historical_ledger_sha256": blobs.get("historical_ledger_physical_sha256") == oracle.get("historical_ledger_sha256"),
        "historical_sidecar": blobs.get("historical_sidecar_matches_ledger") == oracle.get("historical_sidecar_matches"),
        "generator_blob": blobs.get("generator_git_blob_sha") == oracle.get("historical_generator_blob_sha"),
        "generator_output_binding": (generator_binding.get("status") == "PROVEN") == oracle.get("generator_output_binding"),
        "ledger_equality": blobs.get("historical_current_ledger_equality") == oracle.get("current_historical_ledger_equality"),
        "parent_path_absence": all(not record.get("existed_in_parent") for record in history.get("paths", {}).values()) == all(oracle.get("parent_path_absence", {}).values()),
        "ownership": primary["ownership"].get("embedded_row_owner_ids") == oracle.get("embedded_row_owner_ids"),
        "direct_invalidation": invalidation.get("direct_ledger_invalidation_authority") == oracle.get("direct_ledger_invalidation_authority"),
        "implementation_invalidation": invalidation.get("implementation_invalidation_authority") == oracle.get("implementation_invalidation_authority"),
        "derived_invalidation": invalidation.get("derived_ledger_invalidation_authority") == oracle.get("derived_ledger_invalidation_authority"),
        "search_counts": [(item.get("candidate_count"), item.get("inspected_candidate_count"), len(item.get("matching_records", [])), item.get("search_completed")) for item in primary.get("source_searches", [])] == [(item.get("candidate_count"), item.get("inspected_candidate_count"), item.get("matching_record_count"), item.get("search_completed")) for item in oracle.get("search_records", [])],
        "verdict": primary["verdict"] == oracle.get("verdict"),
    }
    return {"status": "AGREEMENT" if all(checks.values()) else "MISMATCH", "checks": checks}


def publish_provenance_evidence(repo_root: Path, output_dir: Path, *, external_roots: Iterable[Path] = ()) -> dict[str, Any]:
    from .build_evidence import build_immutable_evidence

    evidence, source_inventory = build_immutable_evidence(repo_root, external_roots)
    content = (repo_root / LEDGER_RELATIVE_PATH).read_bytes()
    primary = audit_signal_ledger(content, evidence)
    oracle = oracle_audit(repo_root, EXPECTED_LEDGER_SHA256, EXPECTED_ROW_COUNT, external_roots)
    agreement = _agreement(primary, oracle)
    if agreement["status"] != "AGREEMENT":
        raise ValueError("PRIMARY_ORACLE_MISMATCH")
    schema = {"schema_version": "signal_ledger_provenance_v1", "required_safety_flags": SAFETY_FLAGS, "output_names": list(OUTPUT_NAMES)}
    manifest = {**SAFETY_FLAGS, "artifact_semantic_sha256": {}, "searched_source_count": len(source_inventory), "absolute_paths_excluded_from_semantic_hashes": True}
    outputs = {
        "schema.json": schema,
        "signal_ledger_source_inventory.json": {**SAFETY_FLAGS, "sources": source_inventory},
        "signal_ledger_ownership_review.json": {**SAFETY_FLAGS, **primary["ownership"]},
        "signal_ledger_implementation_review.json": {**SAFETY_FLAGS, **primary["implementation"]},
        "signal_ledger_parameter_review.json": {**SAFETY_FLAGS, **primary["parameters"]},
        "signal_ledger_dataset_review.json": {**SAFETY_FLAGS, **primary["dataset"]},
        "signal_ledger_temporal_split_review.json": {**SAFETY_FLAGS, **primary["temporal_split"]},
        "signal_ledger_freeze_contamination_review.json": {**SAFETY_FLAGS, **primary["freeze_contamination"], "historical_invalidation": primary["historical_invalidation"]},
        "signal_ledger_provenance_summary.json": {**SAFETY_FLAGS, "ledger": primary["ledger"], "primary_oracle_agreement": agreement, "verdict": primary["verdict"]},
    }
    manifest["artifact_semantic_sha256"] = {name: semantic_sha256(payload) for name, payload in outputs.items()}
    outputs["external_evidence_manifest.json"] = manifest
    for name, payload in outputs.items():
        _write_json(output_dir / name, payload)
    return {"primary": primary, "oracle": oracle, "agreement": agreement, "semantic_manifest_sha256": semantic_sha256(manifest)}
