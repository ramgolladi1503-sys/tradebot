from __future__ import annotations

import json
from pathlib import Path

from research.option_analytics_v1.evidence import (
    generate_reference_evidence,
    publication_gate,
    run_determinism,
    verify_sha256s,
    write_bundle,
)
from research.option_analytics_v1.legacy_audit import run_legacy_compatibility_audit
from research.option_analytics_v1.packaged_evidence import (
    package_reference_artifact,
    verify_committed_bundle,
    verify_committed_hashes,
)

ROOT = Path(__file__).resolve().parents[3]


def test_oracle_reference_grid_passes_and_reconciles():
    payload = generate_reference_evidence()
    assert payload["input_case_count"] == 96
    assert payload["output_case_count"] == 96
    assert payload["parity_case_count"] == 48
    assert payload["failure_count"] == 0
    assert payload["iv_identifiable_case_count"] + payload["iv_lower_bound_case_count"] == 96


def test_oracle_module_is_independent_of_primary_implementation():
    source = (ROOT / "research/option_analytics_v1/oracle.py").read_text(encoding="utf-8")
    assert "core.option_analytics" not in source
    assert "from .pricing" not in source
    assert "from .greeks" not in source


def test_legacy_audit_confirms_known_contract_defects():
    payload = run_legacy_compatibility_audit(ROOT)
    assert payload["input_case_count"] == payload["output_case_count"]
    assert payload["summary"] == {
        "put_theta_defect": "CONFIRMED",
        "time_to_expiry_defect": "CONFIRMED",
        "solver_convergence_ambiguity": "CONFIRMED",
        "invalid_input_ambiguity": "CONFIRMED",
    }


def test_bundle_hashes_verify(tmp_path):
    write_bundle(ROOT, tmp_path)
    assert verify_sha256s(tmp_path) == []


def test_determinism_ignores_only_declared_manifest_timestamp():
    payload = run_determinism(ROOT)
    assert payload["semantic_hashes_equal"]
    assert payload["failure_count"] == 0


def test_publication_gate_passes_valid_bundle(tmp_path):
    write_bundle(ROOT, tmp_path)
    payload = publication_gate(ROOT, tmp_path)
    assert payload["verdict"] == "PASS_RESEARCH_SIDECAR_GATE"
    assert payload["failure_count"] == 0


def test_publication_gate_fails_tampered_evidence(tmp_path):
    write_bundle(ROOT, tmp_path)
    target = tmp_path / "reference_case_results.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["failure_count"] = 1
    target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    gate = publication_gate(ROOT, tmp_path)
    assert gate["verdict"] == "FAIL_RESEARCH_SIDECAR_GATE"
    assert gate["failure_count"] > 0


def test_packaged_reference_round_trip(tmp_path):
    from research.option_analytics_v1.evidence import write_complete_bundle

    evidence_dir = tmp_path / "evidence"
    write_complete_bundle(ROOT, evidence_dir)
    package_reference_artifact(evidence_dir, remove_plaintext=True)
    payload = verify_committed_bundle(ROOT, evidence_dir)
    assert payload["verdict"] == "PASS_RESEARCH_SIDECAR_GATE"
    assert payload["packaged_reference_verified"]


def test_committed_evidence_bundle_verifies():
    evidence_dir = ROOT / "research/option_analytics_v1/evidence"
    assert verify_committed_hashes(evidence_dir) == []
    payload = verify_committed_bundle(ROOT, evidence_dir)
    assert payload["verdict"] == "PASS_RESEARCH_SIDECAR_GATE"
    assert payload["packaged_reference_verified"]
