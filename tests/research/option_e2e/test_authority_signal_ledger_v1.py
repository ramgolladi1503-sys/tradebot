from __future__ import annotations

import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.provenance_evidence import (
    EXPECTED_DERIVED_REASON,
    EXPECTED_LEDGER_SHA256,
    ProvenanceEvidenceError,
    REQUIRED_EVIDENCE_FILES,
    load_signal_ledger_provenance_evidence,
    semantic_sha256,
)
from research.option_e2e_recertification_v4.all_strategy_authority_closure_v1.signal_authority import (
    CONCLUSIONS,
    assess_signal_ledger_authority,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
EVIDENCE_DIR = Path("research/option_e2e_recertification_v4/signal_ledger_provenance_v1")


def _canonical() -> dict[str, object]:
    return {
        "dataset_family_id": "FAMILY:NIFTY_SPOT:spot:NSE:5m",
        "dataset_version_id": "VERSION:FAMILY:NIFTY_SPOT:spot:NSE:5m:0123456789abcdef",
        "implementation_hash": HASH_A,
        "parameter_hash": HASH_B,
        "dataset_hash": HASH_C,
        "dataset_authority": "CANONICAL_DATASET_VERSION",
        "feature_cutoff_ts": "2026-01-05T09:20:00+05:30",
        "signal_ts": "2026-01-05T09:20:00+05:30",
        "earliest_entry_ts": "2026-01-05T09:21:00+05:30",
        "fold_identity": "walk-forward-fold-03",
        "split_identity": HASH_D,
        "freeze_provenance": "immutable-manifest:signal-freeze-v1",
        "freeze_ts": "2026-01-05T09:20:30+05:30",
        "outcome_available_ts": "2026-01-05T15:30:00+05:30",
        "outcome_or_pnl_contamination": False,
        "option_price_contamination": False,
        "tuned_after_outcome": False,
        "holdout_contamination": False,
        "historically_invalidated": False,
        "signal_id_unique": True,
        "row_count": 12,
    }


def _bound_invalidated() -> dict[str, object]:
    evidence = _canonical()
    evidence.update(
        {
            "physical_hash": EXPECTED_LEDGER_SHA256,
            "provenance_ledger_hash": EXPECTED_LEDGER_SHA256,
            "row_count": 24,
            "provenance_row_count": 24,
            "artifact_kind": "MULTI_OWNER_BLOCKED_PLACEHOLDER_INVENTORY",
            "artifact_verdict": "SIGNAL_LEDGER_INVALIDATED",
            "direct_ledger_invalidation_authority": "UNRESOLVED",
            "implementation_invalidation_authority": "CONFIRMED",
            "derived_ledger_invalidation_authority": "CONFIRMED",
            "derived_invalidation_reason_code": EXPECTED_DERIVED_REASON,
            "generator_output_binding_status": "PROVEN",
            "primary_oracle_agreement": "AGREEMENT",
            "aggregate_canonical_strategy_id": None,
            "research_only": True,
            "read_only": True,
            "allowed_for_live_execution": False,
            "broker_api_called": False,
            "is_order_action": False,
        }
    )
    return evidence


def _write_sidecar(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")


def _copy_evidence(tmp_path: Path) -> Path:
    target = tmp_path / "provenance"
    target.mkdir(parents=True)
    for name in REQUIRED_EVIDENCE_FILES:
        shutil.copy2(EVIDENCE_DIR / name, target / name)
        shutil.copy2(EVIDENCE_DIR / f"{name}.sha256", target / f"{name}.sha256")
    return target


def _reseal_json(evidence_dir: Path, name: str, payload: dict[str, object]) -> None:
    path = evidence_dir / name
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _write_sidecar(path)
    if name == "external_evidence_manifest.json":
        return
    manifest_path = evidence_dir / "external_evidence_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_semantic_sha256"][name] = semantic_sha256(payload)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _write_sidecar(manifest_path)


def test_canonical_ledger_requires_all_independent_authorities() -> None:
    result = assess_signal_ledger_authority(_canonical())

    assert result["authority_conclusion"] == "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER"
    assert set(result["field_authority"].values()) == {"PROVEN", "CLEAR"}
    assert result["authority_reason_codes"] == []
    assert result["read_only"] is True
    assert result["is_order_action"] is False
    assert result["broker_api_called"] is False
    assert result["allowed_for_live_execution"] is False
    assert result["append"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("implementation_hash", ""),
        ("parameter_hash", "not-a-hash"),
        ("dataset_hash", None),
        ("dataset_authority", "CLAIMED"),
        ("feature_cutoff_ts", None),
        ("fold_identity", ""),
        ("split_identity", "d" * 63),
        ("freeze_provenance", None),
        ("outcome_or_pnl_contamination", None),
        ("option_price_contamination", "unknown"),
        ("tuned_after_outcome", None),
        ("holdout_contamination", None),
        ("historically_invalidated", None),
    ],
)
def test_one_missing_authority_field_fails_closed(field: str, value: object) -> None:
    evidence = _canonical()
    evidence[field] = value
    evidence.update({"status": "VALID", "accepted": True, "authority_conclusion": "CANONICAL_PRE_OUTCOME_SIGNAL_LEDGER"})

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "INSUFFICIENT_PROVENANCE"
    assert result["authority_reason_codes"]


def test_limited_but_authoritative_dataset_is_not_promoted_to_canonical() -> None:
    evidence = _canonical()
    evidence["dataset_authority"] = "USABLE_WITH_LIMITATIONS"

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "VALID_PRECOMPUTED_SIGNALS_WITH_LIMITATIONS"
    assert result["field_authority"]["dataset_authority"] == "PROVEN_WITH_LIMITATIONS"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"feature_cutoff_ts": "2026-01-05T09:22:00+05:30"}, "INVALID_SIGNAL_LEDGER"),
        ({"signal_ts": "2026-01-05T09:21:00+05:30"}, "INVALID_SIGNAL_LEDGER"),
        ({"signal_id_unique": False}, "INVALID_SIGNAL_LEDGER"),
        ({"row_count": 0}, "INVALID_SIGNAL_LEDGER"),
        ({"outcome_or_pnl_contamination": True}, "POST_OUTCOME_OR_TUNED"),
        ({"option_price_contamination": True}, "POST_OUTCOME_OR_TUNED"),
        ({"tuned_after_outcome": True}, "POST_OUTCOME_OR_TUNED"),
        ({"freeze_ts": "2026-01-05T15:30:00+05:30"}, "POST_OUTCOME_OR_TUNED"),
        ({"holdout_contamination": True}, "HOLDOUT_CONTAMINATED"),
        ({"historically_invalidated": True}, "INSUFFICIENT_PROVENANCE"),
    ],
)
def test_material_mutations_select_specific_fail_closed_conclusions(
    mutation: dict[str, object], expected: str
) -> None:
    evidence = deepcopy(_canonical())
    evidence.update(mutation)

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == expected
    assert result["authority_conclusion"] in CONCLUSIONS


def test_bare_historical_boolean_cannot_override_holdout_leakage() -> None:
    invalidated = _canonical()
    invalidated.update({"historically_invalidated": True, "holdout_contamination": True, "tuned_after_outcome": True})
    holdout = _canonical()
    holdout.update({"holdout_contamination": True, "tuned_after_outcome": True})

    assert assess_signal_ledger_authority(invalidated)["authority_conclusion"] == "HOLDOUT_CONTAMINATED"
    assert assess_signal_ledger_authority(holdout)["authority_conclusion"] == "HOLDOUT_CONTAMINATED"


def test_derived_invalidation_requires_the_complete_immutable_binding() -> None:
    result = assess_signal_ledger_authority(_bound_invalidated())

    assert result["authority_conclusion"] == "INVALIDATED_HISTORICAL_EVIDENCE"
    assert result["authority_reason_codes"] == ["derived_through_proven_invalidated_generator_binding"]
    assert result["field_authority"]["historical_invalidation"] == "DERIVED_CONFIRMED"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("generator_output_binding_status", "UNRESOLVED", "generator_binding"),
        ("primary_oracle_agreement", "DISAGREEMENT", "primary_oracle"),
        ("implementation_invalidation_authority", "UNRESOLVED", "implementation_authority"),
        ("derived_invalidation_reason_code", "GENERIC_INVALIDATION", "derived_reason"),
        ("provenance_ledger_hash", "f" * 64, "ledger_hash"),
        ("provenance_row_count", 23, "row_count"),
    ],
)
def test_derived_invalidation_contradictions_are_invalid_not_unresolved(
    field: str, value: object, reason: str
) -> None:
    evidence = _bound_invalidated()
    evidence[field] = value

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "INVALID_SIGNAL_LEDGER"
    assert f"derived_invalidation_{reason}_invalid" in result["authority_reason_codes"]


def test_pr711_evidence_loader_accepts_only_the_committed_contract() -> None:
    evidence = load_signal_ledger_provenance_evidence(EVIDENCE_DIR)

    assert evidence.physical_hash == EXPECTED_LEDGER_SHA256
    assert evidence.row_count == 24
    assert evidence.direct_ledger_invalidation_authority == "UNRESOLVED"
    assert evidence.implementation_invalidation_authority == "CONFIRMED"
    assert evidence.derived_ledger_invalidation_authority == "CONFIRMED"
    assert evidence.canonical_strategy_id is None


def test_pr711_evidence_loader_rejects_missing_and_tampered_files(tmp_path: Path) -> None:
    missing = _copy_evidence(tmp_path / "missing")
    (missing / "signal_ledger_ownership_review.json").unlink()
    with pytest.raises(ProvenanceEvidenceError, match="MISSING_FILE"):
        load_signal_ledger_provenance_evidence(missing)

    tampered = _copy_evidence(tmp_path / "tampered")
    sidecar = tampered / "signal_ledger_provenance_summary.json.sha256"
    sidecar.write_text(f"{'0' * 64}  signal_ledger_provenance_summary.json\n", encoding="utf-8")
    with pytest.raises(ProvenanceEvidenceError, match="SIDECAR_MISMATCH"):
        load_signal_ledger_provenance_evidence(tampered)


@pytest.mark.parametrize(
    ("name", "mutate", "failure"),
    [
        (
            "signal_ledger_provenance_summary.json",
            lambda payload: payload["ledger"].__setitem__("physical_sha256", "f" * 64),
            "HASH_MISMATCH",
        ),
        (
            "signal_ledger_provenance_summary.json",
            lambda payload: payload["ledger"].__setitem__("row_count", 23),
            "ROW_COUNT_MISMATCH",
        ),
        (
            "signal_ledger_provenance_summary.json",
            lambda payload: payload["primary_oracle_agreement"].__setitem__("status", "DISAGREEMENT"),
            "PRIMARY_ORACLE_DISAGREEMENT",
        ),
        (
            "signal_ledger_implementation_review.json",
            lambda payload: payload["historical_binding"]["generator_output_binding"].__setitem__("status", "UNRESOLVED"),
            "MISSING_GENERATOR_BINDING",
        ),
        (
            "signal_ledger_freeze_contamination_review.json",
            lambda payload: payload.__setitem__("implementation_invalidation_authority", "UNRESOLVED"),
            "INVALIDATION_CONTRADICTION",
        ),
        (
            "signal_ledger_freeze_contamination_review.json",
            lambda payload: payload["historical_invalidation"].__setitem__("derived_reason_code", "GENERIC"),
            "WRONG_REASON_CODE",
        ),
        (
            "signal_ledger_provenance_summary.json",
            lambda payload: payload.__setitem__("allowed_for_live_execution", True),
            "UNSAFE_SAFETY_FLAG",
        ),
    ],
)
def test_pr711_evidence_semantic_mutations_fail_with_specific_codes(
    tmp_path: Path, name: str, mutate, failure: str
) -> None:
    evidence_dir = _copy_evidence(tmp_path)
    payload = json.loads((evidence_dir / name).read_text(encoding="utf-8"))
    mutate(payload)
    _reseal_json(evidence_dir, name, payload)

    with pytest.raises(ProvenanceEvidenceError, match=failure):
        load_signal_ledger_provenance_evidence(evidence_dir)


def test_pr711_evidence_loader_rejects_malformed_json_after_physical_reseal(tmp_path: Path) -> None:
    evidence_dir = _copy_evidence(tmp_path)
    malformed = evidence_dir / "signal_ledger_provenance_summary.json"
    malformed.write_text("{not-json}\n", encoding="utf-8")
    _write_sidecar(malformed)

    with pytest.raises(ProvenanceEvidenceError, match="MALFORMED_JSON"):
        load_signal_ledger_provenance_evidence(evidence_dir)


def test_non_mapping_input_is_invalid_and_cannot_raise_open() -> None:
    result = assess_signal_ledger_authority(None)  # type: ignore[arg-type]

    assert result["authority_conclusion"] == "INVALID_SIGNAL_LEDGER"
    assert result["authority_reason_codes"] == ["ledger_not_mapping"]


def test_malformed_contamination_value_fails_closed_without_raising() -> None:
    evidence = _canonical()
    evidence["option_price_contamination"] = {"claimed": False}

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "INSUFFICIENT_PROVENANCE"
    assert "option_price_contamination_unproven" in result["authority_reason_codes"]


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("dataset_family_id", "VERSION:FAMILY:NIFTY_SPOT:spot:NSE:5m:0123456789abcdef", "dataset_family_id_invalid"),
        ("dataset_version_id", "FAMILY:NIFTY_SPOT:spot:NSE:5m", "dataset_version_id_invalid"),
    ],
)
def test_dataset_authority_identifiers_are_typed_and_cannot_be_interchanged(
    field: str, value: str, reason: str
) -> None:
    evidence = _canonical()
    evidence[field] = value

    result = assess_signal_ledger_authority(evidence)

    assert result["authority_conclusion"] == "INVALID_SIGNAL_LEDGER"
    assert reason in result["authority_reason_codes"]
