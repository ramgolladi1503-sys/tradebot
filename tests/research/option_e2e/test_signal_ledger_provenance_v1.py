from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.option_e2e_recertification_v4.signal_ledger_provenance_v1 import (
    AuditError,
    audit_signal_ledger,
    oracle_audit,
    publish_provenance_evidence,
    semantic_sha256,
)


def _ledger(*, rows: int = 2, temporal: bool = False, fold: bool = False) -> bytes:
    records = []
    for index in range(rows):
        records.append(
            {
                "strategy_or_hypothesis_id": f"STRATEGY_{index}",
                "signal_id": f"signal-{index}",
                "feature_cutoff_ts": "2026-01-01T09:20:00+05:30" if temporal else "",
                "signal_ts": "2026-01-01T09:21:00+05:30" if temporal else "",
                "earliest_entry_ts": "2026-01-01T09:22:00+05:30" if temporal else "",
                "fold_id": "development-1" if fold else "",
            }
        )
    return (json.dumps({"records": records}, sort_keys=True) + "\n").encode()


def _evidence(content: bytes) -> dict[str, object]:
    digest = hashlib.sha256(content).hexdigest()
    return {
        "implementation_manifest": {"ledger_sha256": digest, "commit_sha": "c" * 40, "path": "generator.py", "git_blob_sha": "b" * 40, "content_sha256": "a" * 64},
        "parameter_manifest": {"ledger_sha256": digest, "complete": True, "owner": "STRATEGY_0", "parameters": [{"name": "threshold", "value": 1, "type": "int"}]},
        "dataset_manifest": {"ledger_sha256": digest, "dataset_family_id": "FAMILY:NIFTY:spot:NSE:1m", "dataset_version_id": "VERSION:one", "dataset_content_sha256": "d" * 64, "session_set_hash": "e" * 64, "date_range": "2026-01-01/2026-01-02", "row_count": 10, "instrument_identity": "NIFTY", "timezone": "Asia/Kolkata", "bar_interval": "1m"},
        "split_manifest": {"ledger_sha256": digest, "split_identity": "development"},
        "freeze_manifest": {"ledger_sha256": digest, "commit_sha": "c" * 40},
        "contamination_evidence": {"outcome": "CLEAR", "option_price": "CLEAR", "tuning": "CLEAR", "holdout": "CLEAR"},
    }


def _audit(content: bytes, evidence: dict[str, object]) -> dict[str, object]:
    return audit_signal_ledger(content, evidence, expected_sha256=hashlib.sha256(content).hexdigest(), expected_row_count=2)


def test_physical_hash_mismatch_fails_closed() -> None:
    with pytest.raises(AuditError, match="LEDGER_PHYSICAL_HASH_MISMATCH"):
        audit_signal_ledger(_ledger(), {}, expected_sha256="0" * 64, expected_row_count=2)


def test_row_count_mismatch_fails_closed() -> None:
    content = _ledger()
    with pytest.raises(AuditError, match="LEDGER_ROW_COUNT_MISMATCH"):
        audit_signal_ledger(content, {}, expected_sha256=hashlib.sha256(content).hexdigest(), expected_row_count=3)


@pytest.mark.parametrize("basis", ["FILENAME_ONLY", "DIRECTORY_ONLY"])
def test_location_only_ownership_is_rejected(basis: str) -> None:
    content = _ledger()
    result = _audit(content, {"ownership_basis": basis})
    assert result["ownership"]["ownership_status"] == "UNRESOLVED"
    assert result["verdict"] == "SIGNAL_LEDGER_PROVENANCE_BLOCKED"


def test_hash_protected_embedded_ownership_is_accepted() -> None:
    content = _ledger()
    result = _audit(content, {})
    assert result["ownership"]["canonical_strategy_ids"] == ["STRATEGY_0", "STRATEGY_1"]
    assert result["ownership"]["ownership_status"] == "PROVEN_WITH_LIMITATIONS"


def test_conflicting_manifest_owner_invalidates() -> None:
    content = _ledger()
    evidence = {"ownership_manifest": {"ledger_sha256": hashlib.sha256(content).hexdigest(), "canonical_strategy_ids": ["DIFFERENT"]}}
    result = _audit(content, evidence)
    assert result["ownership"]["ownership_status"] == "CONFLICTING"
    assert result["verdict"] == "SIGNAL_LEDGER_INVALIDATED"


def test_current_code_without_ledger_binding_is_rejected() -> None:
    content = _ledger()
    result = _audit(content, {"implementation_manifest": {"commit_sha": "c" * 40}, "candidate_current_implementation_hash": "a" * 64})
    assert result["implementation"]["implementation_authority"] == "UNRESOLVED"
    assert result["implementation"]["candidate_current_implementation_hash"] == "a" * 64


def test_implementation_commit_and_hash_binding_is_preserved() -> None:
    content = _ledger()
    result = _audit(content, _evidence(content))
    assert result["implementation"]["ledger_proven_implementation_commit"] == "c" * 40
    assert result["implementation"]["ledger_proven_implementation_blob_hash"] == "b" * 40


def test_incomplete_parameter_manifest_remains_unresolved() -> None:
    content = _ledger()
    evidence = _evidence(content)
    evidence["parameter_manifest"] = {"ledger_sha256": hashlib.sha256(content).hexdigest(), "complete": True, "parameters": []}
    result = _audit(content, evidence)
    assert result["parameters"]["parameter_authority"] == "UNRESOLVED"
    assert result["parameters"]["missing_parameter_fields"] != []


def test_dataset_requires_typed_family_and_version_ids() -> None:
    content = _ledger()
    evidence = _evidence(content)
    evidence["dataset_manifest"]["dataset_family_id"] = "NIFTY"
    result = _audit(content, evidence)
    assert result["dataset"]["dataset_authority"] == "UNRESOLVED"
    assert result["dataset"]["dataset_family_id"] == "NIFTY"


def test_missing_temporal_and_fold_fields_remain_unresolved() -> None:
    content = _ledger()
    result = _audit(content, _evidence(content))
    assert result["temporal_split"]["temporal_authority"] == "UNRESOLVED"
    assert result["temporal_split"]["split_authority"] == "UNRESOLVED"


def test_invalid_causal_ordering_invalidates() -> None:
    content = _ledger(temporal=True, fold=True)
    payload = json.loads(content)
    payload["records"][0]["earliest_entry_ts"] = "2026-01-01T09:19:00+05:30"
    mutated = (json.dumps(payload, sort_keys=True) + "\n").encode()
    result = _audit(mutated, _evidence(mutated))
    assert result["temporal_split"]["causal_ordering_result"] == "INVALID_CAUSAL_ORDERING"
    assert result["verdict"] == "SIGNAL_LEDGER_INVALIDATED"


def test_missing_freeze_manifest_blocks_complete_provenance() -> None:
    content = _ledger(temporal=True, fold=True)
    evidence = _evidence(content)
    del evidence["freeze_manifest"]
    result = _audit(content, evidence)
    assert result["freeze_contamination"]["freeze_authority"] == "UNRESOLVED"
    assert result["verdict"] == "SIGNAL_LEDGER_OWNERSHIP_PROVEN_BUT_PROVENANCE_INCOMPLETE"


def test_unresolved_contamination_states_do_not_become_clear() -> None:
    content = _ledger(temporal=True, fold=True)
    evidence = _evidence(content)
    evidence["contamination_evidence"] = {}
    result = _audit(content, evidence)
    assert result["freeze_contamination"]["outcome_contamination_authority"] == "UNRESOLVED"
    assert result["verdict"] == "SIGNAL_LEDGER_OWNERSHIP_PROVEN_BUT_PROVENANCE_INCOMPLETE"


def test_confirmed_contamination_invalidates() -> None:
    content = _ledger(temporal=True, fold=True)
    evidence = _evidence(content)
    evidence["contamination_evidence"]["holdout"] = "CONFIRMED"
    result = _audit(content, evidence)
    assert result["freeze_contamination"]["holdout_contamination_authority"] == "CONFIRMED"
    assert result["verdict"] == "SIGNAL_LEDGER_INVALIDATED"


def test_historical_invalidation_invalidates() -> None:
    content = _ledger()
    evidence = _evidence(content)
    evidence["historical_invalidation"] = {"ledger_sha256": hashlib.sha256(content).hexdigest(), "decision": "INVALID"}
    result = _audit(content, evidence)
    assert result["freeze_contamination"]["historical_invalidation_authority"] == "CONFIRMED"
    assert result["verdict"] == "SIGNAL_LEDGER_INVALIDATED"


def test_independent_oracle_reports_bindings_without_primary_call() -> None:
    content = _ledger(temporal=True, fold=True)
    digest = hashlib.sha256(content).hexdigest()
    result = oracle_audit(content, _evidence(content), digest, 2)
    assert result["bindings"]["implementation"] is True
    assert result["bindings"]["historical_invalidation"] is False


def test_primary_oracle_mismatch_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = _ledger()
    ledger = tmp_path / "ledger.json"
    ledger.write_bytes(content)
    monkeypatch.setattr("research.option_e2e_recertification_v4.signal_ledger_provenance_v1.generate.EXPECTED_LEDGER_SHA256", hashlib.sha256(content).hexdigest())
    monkeypatch.setattr("research.option_e2e_recertification_v4.signal_ledger_provenance_v1.generate.EXPECTED_ROW_COUNT", 2)
    monkeypatch.setattr("research.option_e2e_recertification_v4.signal_ledger_provenance_v1.generate.oracle_audit", lambda *args: {"physical_hash_matches": True, "row_count_matches": True, "canonical_strategy_ids": ["MUTATED"], "bindings": {name: False for name in ("implementation", "parameters", "dataset", "temporal", "split_fold", "freeze")}, "verdict": "SIGNAL_LEDGER_PROVENANCE_BLOCKED"})
    with pytest.raises(ValueError, match="PRIMARY_ORACLE_MISMATCH"):
        publish_provenance_evidence(ledger, {}, [], tmp_path / "out")


def test_semantic_hash_is_path_independent() -> None:
    first = {"semantic_path": "ledger.json", "value": 1}
    second = {"value": 1, "semantic_path": "ledger.json"}
    mutated = {"semantic_path": "/absolute/ledger.json", "value": 1}
    assert semantic_sha256(first) == semantic_sha256(second)
    assert semantic_sha256(first) != semantic_sha256(mutated)


def test_publication_writes_sidecars_and_safety_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = _ledger()
    digest = hashlib.sha256(content).hexdigest()
    ledger = tmp_path / "ledger.json"
    ledger.write_bytes(content)
    monkeypatch.setattr("research.option_e2e_recertification_v4.signal_ledger_provenance_v1.generate.EXPECTED_LEDGER_SHA256", digest)
    monkeypatch.setattr("research.option_e2e_recertification_v4.signal_ledger_provenance_v1.generate.EXPECTED_ROW_COUNT", 2)
    output = tmp_path / "published"
    publish_provenance_evidence(ledger, {}, [{"category": "TEST"}], output)
    summary = json.loads((output / "signal_ledger_provenance_summary.json").read_text())
    sidecar_digest = (output / "signal_ledger_provenance_summary.json.sha256").read_text().split()[0]
    assert summary["research_only"] is True
    assert summary["allowed_for_live_execution"] is False
    assert summary["outcomes_read"] is False
    assert sidecar_digest == hashlib.sha256((output / "signal_ledger_provenance_summary.json").read_bytes()).hexdigest()
