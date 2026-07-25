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
        {"canonical_strategy_id": "S2", "priority": "P3", "priority_class": "P3", "authority_status": "BLOCKED", "upstream_readiness_blocker": "SOURCE"},
        {"canonical_strategy_id": "S1", "priority": "P2", "priority_class": "P2", "authority_status": "BLOCKED", "upstream_readiness_blocker": "SIGNAL"},
    ]
    return {
        "input": {"authority_status": "PASS", "dataset_families": 2, "dataset_versions": 3, "canonical_signal_ledgers": 0, "strategy_lanes": 2},
        "families": families,
        "versions": [
            {"dataset_version_id": "V1", "authority_decision": "KEEP"},
            {"dataset_version_id": "V2", "authority_decision": "KEEP"},
            {"dataset_version_id": "V3", "authority_decision": "REJECT"},
        ],
        "signal": {
            "authority_status": "BLOCKED",
            "signal_ledger_id": "b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed:24",
            "physical_hash": "b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed",
            "row_count": 24,
            "signal_ledger_candidate_count": 1,
            "authority_conclusion": "INVALIDATED_HISTORICAL_EVIDENCE",
            "artifact_kind": "MULTI_OWNER_BLOCKED_PLACEHOLDER_INVENTORY",
            "direct_ledger_invalidation_authority": "UNRESOLVED",
            "implementation_invalidation_authority": "CONFIRMED",
            "derived_ledger_invalidation_authority": "CONFIRMED",
            "derived_invalidation_reason_code": "DERIVED_THROUGH_PROVEN_INVALIDATED_GENERATOR_BINDING",
            "generator_output_binding_status": "PROVEN",
            "primary_oracle_agreement": "AGREEMENT",
            "canonical_strategy_id": None,
            "canonical_signal_ledger_count": 0,
            "usable_signal_ledger_count": 0,
            "invalidated_signal_ledger_count": 1,
            "replacement_signal_ledger_required": True,
            "lane_impact_analysis": {
                "evaluated_lane_count": 2,
                "previous_affected_lane_count": 0,
                "new_affected_lane_count": 0,
                "affected_lane_assignments": [],
                "new_executable_lane_count": 0,
                "executable_lane_delta": 0,
                "new_valid_precomputed_signal_lane_count": 0,
                "valid_precomputed_signal_lane_delta": 0,
                "removed_lane_blocker_count": 0,
                "lane_blocker_delta": "NONE",
                "reason": "INVALIDATED_MULTI_OWNER_PLACEHOLDER_WAS_NOT_CANONICALLY_ASSIGNED",
            },
            "blocker_delta": {
                "previous_blocker_record_count": 2,
                "new_blocker_record_count": 2,
                "previous_affected_lane_count": 2,
                "new_affected_lane_count": 2,
                "added_blocker_ids": [],
                "removed_blocker_ids": [],
                "changed_blocker_ids": [],
                "lane_blocker_delta": "NONE",
                "reason": "INVALIDATED_MULTI_OWNER_PLACEHOLDER_WAS_NOT_CANONICALLY_ASSIGNED",
            },
        },
        "unresolved": {"authority_status": "BLOCKED", "unresolved_candidate_count": 4, "material_truncated_roots": 2},
        "strategies": [
            {"canonical_strategy_id": "S1", "authority_status": "BLOCKED", "signal_authority": "NOT_APPLICABLE", "signal_ledger_status": "NOT_APPLICABLE", "upstream_readiness_blocker": "SIGNAL", "current_blocker_ids": ["B1"]},
            {"canonical_strategy_id": "S2", "authority_status": "BLOCKED", "signal_authority": "UNRESOLVED", "signal_ledger_status": "NO_SIGNAL_LEDGER", "upstream_readiness_blocker": "SOURCE", "current_blocker_ids": ["B2"]},
        ],
        "blockers": [
            {"blocker_id": "B1", "blocker_class": "SIGNAL", "affected_strategy_ids": ["S1"]},
            {"blocker_id": "B2", "blocker_class": "SOURCE_SEARCH", "affected_strategy_ids": ["S2"]},
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
    assert compact["blocker_summary.json"]["blocker_record_count"] == 2
    assert compact["blocker_summary.json"]["affected_lane_count"] == 2
    assert compact["strategy_authority_summary.json"]["signal_authority_counts"] == {"NOT_APPLICABLE": 1, "UNRESOLVED": 1}
    assert compact["strategy_authority_summary.json"]["upstream_readiness_blocker_counts"] == {"SIGNAL": 1, "SOURCE": 1}
    assert "remaining_blocker_counts" not in compact["strategy_authority_summary.json"]
    assert compact["priority_summary.json"]["ordered_strategy_ids"] == ["S1", "S2"]
    assert compact["authority_closure_summary.json"]["safety"]["allowed_for_live_execution"] is False
    assert compact["authority_closure_summary.json"]["invalidated_signal_ledger_count"] == 1
    assert compact["authority_closure_summary.json"]["replacement_signal_ledger_required"] is True
    assert compact["blocker_summary.json"]["signal_ledger_integration_delta"]["lane_blocker_delta"] == "NONE"
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
        (lambda full: full["strategies"].pop(0), "strategy_lanes"),
        (lambda full: full["strategies"][0].__setitem__("authority_status", "PROVEN"), "status_reconciliation_failed"),
        (lambda full: full["priorities"].append(deepcopy(full["priorities"][0])), "priority_strategy_ids_not_unique"),
        (lambda full: full["blockers"][0].__setitem__("affected_strategy_ids", [""]), "invalid_affected_strategy_ids"),
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


def test_repeated_blocker_classes_aggregate_records_and_unique_lanes() -> None:
    full = _full_payloads()
    for strategy in full["strategies"]:  # type: ignore[union-attr]
        strategy["current_blocker_ids"] = []
    blockers = []
    for index in range(98):
        lane_index = index % 2
        lane_id = f"S{lane_index + 1}"
        blocker_id = f"B{index:03d}"
        blocker_class = "DATASET" if index < 64 else "SOURCE_SEARCH"
        blockers.append({"blocker_id": blocker_id, "blocker_class": blocker_class, "affected_strategy_ids": [lane_id]})
        full["strategies"][lane_index]["current_blocker_ids"].append(blocker_id)  # type: ignore[index]
    full["blockers"] = blockers
    full["signal"]["blocker_delta"].update(  # type: ignore[index]
        previous_blocker_record_count=98,
        new_blocker_record_count=98,
    )

    summary = generate_compact_payloads(full)["blocker_summary.json"]

    assert summary["blocker_record_count"] == 98
    assert summary["blocker_record_count_by_class"] == {"DATASET": 64, "SOURCE_SEARCH": 34}
    assert sum(summary["blocker_record_count_by_class"].values()) == summary["blocker_record_count"]
    assert summary["affected_lane_count"] == 2
    assert summary["affected_lane_count_by_class"] == {"DATASET": 2, "SOURCE_SEARCH": 2}


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
