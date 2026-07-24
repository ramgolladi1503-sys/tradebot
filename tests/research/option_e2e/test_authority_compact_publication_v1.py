from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.compact_publication import (
    COMPACT_ARTIFACTS,
    CompactReconciliationError,
    NonPortableSemanticContentError,
    StaleFullArtifactError,
    build_authority_compact_publication,
    generate_compact_payloads,
    semantic_hash,
)


def _full_payloads() -> dict[str, object]:
    families = [
        {"dataset_family_id": "FAMILY:A", "authority_status": "BLOCKED"},
        {"dataset_family_id": "FAMILY:B", "authority_status": "USABLE_WITH_LIMITATIONS"},
    ]
    priorities = [
        {"canonical_strategy_id": "S2", "priority": 2, "authority_status": "BLOCKED", "remaining_blocker": "SOURCE"},
        {"canonical_strategy_id": "S1", "priority": 1, "authority_status": "BLOCKED", "remaining_blocker": "SIGNAL"},
    ]
    return {
        "input": {"authority_status": "PASS", "dataset_families": 2, "dataset_versions": 3, "canonical_signal_ledgers": 0},
        "families": families,
        "versions": [
            {"dataset_version_id": "V1", "authority_decision": "KEEP"},
            {"dataset_version_id": "V2", "authority_decision": "KEEP"},
            {"dataset_version_id": "V3", "authority_decision": "REJECT"},
        ],
        "signal": {"authority_status": "BLOCKED", "canonical_signal_ledger_count": 0, "reason": "missing_provenance"},
        "unresolved": {"authority_status": "BLOCKED", "unresolved_candidate_count": 4, "material_truncated_roots": 2},
        "strategies": [
            *[{"authority_kind": "dataset_family", "authority_target": row["dataset_family_id"], "authority_status": row["authority_status"]} for row in families],
            *[{"authority_kind": "strategy_hypothesis", "authority_target": row["canonical_strategy_id"], "authority_status": row["authority_status"]} for row in priorities],
        ],
        "blockers": [
            {"blocker_class": "SIGNAL", "blocked_lane_count": 1},
            {"blocker_class": "SOURCE", "blocked_lane_count": 1},
        ],
        "priorities": priorities,
    }


def _write_full(directory: Path, payloads: dict[str, object]) -> None:
    names = {
        "input": "input_census_integrity.json", "families": "dataset_family_authority_reviews.json",
        "versions": "dataset_version_authority_decisions.json", "signal": "signal_ledger_authority_review.json",
        "unresolved": "unresolved_source_authority_review.json", "strategies": "all_strategy_authority_matrix.json",
        "blockers": "authority_blocker_ledger.json", "priorities": "strategy_authority_prioritization.json",
    }
    directory.mkdir()
    for key, name in names.items():
        path = directory / name
        path.write_text(json.dumps(payloads[key], sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        (directory / f"{name}.sha256").write_text(f"{digest}  {name}\n", encoding="utf-8")


def test_generates_all_reconciled_compact_payloads_from_fixture() -> None:
    full = _full_payloads()
    compact = generate_compact_payloads(full)

    assert tuple(compact) == COMPACT_ARTIFACTS
    assert compact["dataset_family_authority_summary.json"]["authority_status_counts"] == {
        "BLOCKED": 1, "USABLE_WITH_LIMITATIONS": 1
    }
    assert compact["dataset_version_authority_summary.json"]["authority_decision_counts"] == {"KEEP": 2, "REJECT": 1}
    assert compact["blocker_summary.json"]["blocked_lane_count"] == 2
    assert compact["priority_summary.json"]["ordered_strategy_ids"] == ["S1", "S2"]
    assert compact["authority_closure_summary.json"]["safety"]["allowed_for_live_execution"] is False
    assert compact["external_evidence_manifest.json"]["safety"]["broker_api_called"] is False


def test_semantic_links_change_when_full_authority_evidence_changes() -> None:
    baseline = generate_compact_payloads(_full_payloads())
    mutated_full = deepcopy(_full_payloads())
    mutated_full["versions"][2]["authority_decision"] = "QUARANTINE"  # type: ignore[index]
    mutated = generate_compact_payloads(mutated_full)

    baseline_summary = baseline["dataset_version_authority_summary.json"]
    mutated_summary = mutated["dataset_version_authority_summary.json"]
    assert baseline_summary["source"]["semantic_sha256"] != mutated_summary["source"]["semantic_sha256"]
    assert baseline_summary["authority_decision_counts"] != mutated_summary["authority_decision_counts"]
    manifest_link = mutated["external_evidence_manifest.json"]["compact_artifacts"]["dataset_version_authority_summary.json"]
    assert manifest_link["semantic_sha256"] == semantic_hash(mutated_summary)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda full: full["input"].__setitem__("dataset_versions", 99), "dataset_versions"),
        (lambda full: full["strategies"].pop(0), "matrix_dataset_families"),
        (lambda full: full["strategies"][0].__setitem__("authority_status", "PROVEN"), "status_reconciliation_failed"),
        (lambda full: full["priorities"].append(deepcopy(full["priorities"][0])), "priority_strategy_ids_not_unique"),
        (lambda full: full["blockers"][0].__setitem__("blocked_lane_count", -1), "invalid_count_map"),
    ],
)
def test_reconciliation_mutations_fail_closed(mutation, message: str) -> None:
    full = _full_payloads()
    mutation(full)
    with pytest.raises(CompactReconciliationError, match=message):
        generate_compact_payloads(full)


def test_absolute_paths_are_rejected_from_semantic_content() -> None:
    full = _full_payloads()
    full["unresolved"]["diagnostic_path"] = "/private/tmp/evidence.json"  # type: ignore[index]
    with pytest.raises(NonPortableSemanticContentError, match="absolute_path_in_semantic_content"):
        generate_compact_payloads(full)


def test_builder_writes_optional_physical_sidecars_and_detects_stale_full_artifact(tmp_path: Path) -> None:
    source = tmp_path / "full"
    output = tmp_path / "compact"
    _write_full(source, _full_payloads())

    build_authority_compact_publication(full_authority_dir=source, output_dir=output)
    for name in COMPACT_ARTIFACTS:
        artifact = output / name
        sidecar = output / f"{name}.sha256"
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == sidecar.read_text(encoding="utf-8").split()[0]

    no_sidecars = tmp_path / "without-sidecars"
    build_authority_compact_publication(full_authority_dir=source, output_dir=no_sidecars, physical_sidecars=False)
    assert not list(no_sidecars.glob("*.sha256"))

    stale = source / "authority_blocker_ledger.json"
    stale.write_text(stale.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(StaleFullArtifactError, match="stale_full_artifact"):
        build_authority_compact_publication(full_authority_dir=source, output_dir=tmp_path / "rejected")
