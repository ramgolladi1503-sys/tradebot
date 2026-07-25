from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .audit import EXPECTED_LEDGER_SHA256, EXPECTED_ROW_COUNT, SAFETY_FLAGS, audit_signal_ledger, semantic_sha256
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
    checks = {
        "physical_hash": oracle["physical_hash_matches"] and primary["ledger"]["physical_sha256"] == EXPECTED_LEDGER_SHA256,
        "row_count": oracle["row_count_matches"] and primary["ledger"]["row_count"] == EXPECTED_ROW_COUNT,
        "ownership": primary["ownership"]["canonical_strategy_ids"] == oracle["canonical_strategy_ids"],
        "implementation": (primary["implementation"]["implementation_authority"] != "UNRESOLVED") == oracle["bindings"]["implementation"],
        "parameters": (primary["parameters"]["parameter_authority"] == "PROVEN") == oracle["bindings"]["parameters"],
        "dataset": (primary["dataset"]["dataset_authority"] == "PROVEN") == oracle["bindings"]["dataset"],
        "temporal": (primary["temporal_split"]["temporal_authority"] == "PROVEN") == oracle["bindings"]["temporal"],
        "split_fold": (primary["temporal_split"]["split_authority"] == "PROVEN") == oracle["bindings"]["split_fold"],
        "freeze": (primary["freeze_contamination"]["freeze_authority"] == "PROVEN") == oracle["bindings"]["freeze"],
        "verdict": primary["verdict"] == oracle["verdict"],
    }
    return {"status": "AGREEMENT" if all(checks.values()) else "MISMATCH", "checks": checks}


def publish_provenance_evidence(ledger_path: Path, evidence: Mapping[str, Any], source_inventory: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    content = ledger_path.read_bytes()
    primary = audit_signal_ledger(
        content,
        evidence,
        expected_sha256=EXPECTED_LEDGER_SHA256,
        expected_row_count=EXPECTED_ROW_COUNT,
    )
    oracle = oracle_audit(content, evidence, EXPECTED_LEDGER_SHA256, EXPECTED_ROW_COUNT)
    agreement = _agreement(primary, oracle)
    if agreement["status"] != "AGREEMENT":
        raise ValueError("PRIMARY_ORACLE_MISMATCH")
    schema = {"schema_version": "signal_ledger_provenance_v1", "required_safety_flags": SAFETY_FLAGS, "output_names": list(OUTPUT_NAMES)}
    manifest = {
        **SAFETY_FLAGS,
        "artifact_semantic_sha256": {},
        "searched_source_count": len(source_inventory),
        "absolute_paths_excluded_from_semantic_hashes": True,
    }
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
