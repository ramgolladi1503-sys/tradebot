import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import pytest

from core.certified_release_store import ReleaseStore, ReleaseStoreError
from core.release_certification import certify, EVALUATOR_VERSION
from core.release_change_impact import DependencyEvidence
from core.release_gate_registry import (
    EVALUATOR_VERSION_V2,
    GATE_REGISTRY,
    is_generic_exit_code_zero_placeholder,
    validate_gate_predicate_v2,
)
from scripts.generate_evidence_integrity_primitive import evaluate_evidence_integrity
from scripts.generate_option_mirror_primitive import evaluate_option_mirror_semantics
from scripts.generate_security_authority_primitive import evaluate_security_authority


def test_gate_registry_contains_all_18_gates():
    assert len(GATE_REGISTRY) == 18
    assert "option_mirror" in GATE_REGISTRY
    assert "evidence_integrity" in GATE_REGISTRY
    assert "security_authority" in GATE_REGISTRY


def test_option_mirror_semantics_genuine_pass():
    ok, ev, out = evaluate_option_mirror_semantics()
    assert ok is True
    assert ev["offline_readiness_transition_valid"] is True
    assert ev["degraded_fallback_verified"] is True
    assert ev["stale_mirror_non_fatal_verified"] is True
    assert ev["missing_mirror_fail_closed_verified"] is True


def test_option_mirror_fake_ready_fails_closed():
    observed = {
        "command": "python3 scripts/generate_option_mirror_primitive.py",
        "exit_code": 0,
        "raw_stdout_sha256": "a" * 64,
        "offline_readiness_transition_valid": False,  # Fake readiness
        "degraded_fallback_verified": True,
    }
    assert validate_gate_predicate_v2("option_mirror", observed, Path("."), "a" * 40) is False


def test_evidence_integrity_evaluates_bundle():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "g1.json").write_text("{\"gate\": \"g1\"}")
        (root / "g2.json").write_text("{\"gate\": \"g2\"}")
        manifest = root / "primitive_manifest.json"
        manifest.write_text(json.dumps({"g1": "g1.json", "g2": "g2.json"}))
        ok, ev, out = evaluate_evidence_integrity(root, manifest, "c" * 40)
        assert ok is True
        assert ev["manifest_present"] is True
        assert ev["artifact_paths_safe"] is True
        assert ev["zero_primitive_reuse"] is True
        assert len(ev["bundle_digest"]) == 64


def test_evidence_integrity_rejects_path_escape():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        manifest = root / "primitive_manifest.json"
        manifest.write_text(json.dumps({"g1": "../escape.json"}))
        ok, ev, out = evaluate_evidence_integrity(root, manifest, "c" * 40)
        assert ok is False
        assert ev.get("artifact_paths_safe") is False


def test_evidence_integrity_rejects_primitive_reuse():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "common.json").write_text("{\"gate\": \"common\"}")
        manifest = root / "primitive_manifest.json"
        manifest.write_text(json.dumps({"g1": "common.json", "g2": "common.json"}))
        ok, ev, out = evaluate_evidence_integrity(root, manifest, "c" * 40)
        assert ok is False
        assert ev.get("zero_primitive_reuse") is False


def test_security_authority_evaluates_spy_and_isolation():
    repo = Path(".")
    ok, ev, out = evaluate_security_authority(repo, "d6ee1defd23d1f6c2396cb971f1eeee634277872")
    assert ok is True
    assert ev["singular_candidate_selection_authority_verified"] is True
    assert ev["observer_execution_isolation_verified"] is True
    assert ev["broker_write_calls_measured"] == 0
    assert ev["order_actions_measured"] == 0
    assert ev["measurement_method"] == "spy_counter_verified"


def test_security_authority_constant_forgery_rejected():
    observed = {
        "command": "python3 scripts/generate_security_authority_primitive.py",
        "exit_code": 0,
        "raw_stdout_sha256": "b" * 64,
        "singular_candidate_selection_authority_verified": True,
        "singular_execution_authority_verified": True,
        "observer_execution_isolation_verified": True,
        "broker_write_calls_measured": 0,
        "order_actions_measured": 0,
        "measurement_method": "caller_constant_forgery",  # Not measured via spy
    }
    assert validate_gate_predicate_v2("security_authority", observed, Path("."), "a" * 40) is False


def test_generic_exit_code_zero_placeholder_detected():
    placeholder = {"command": "governed:persistence", "exit_code": 0}
    assert is_generic_exit_code_zero_placeholder(placeholder) is True


def test_generator_writes_companion_stdout(tmp_path):
    import subprocess
    candidate = "d6ee1defd23d1f6c2396cb971f1eeee634277872"

    # 1. Option mirror
    out_opt = tmp_path / "option_mirror.json"
    subprocess.run(["python3", "scripts/generate_option_mirror_primitive.py", "--candidate", candidate, "--output", str(out_opt)], check=True)
    assert out_opt.exists()
    assert out_opt.with_suffix(".stdout").exists()
    payload = json.loads(out_opt.read_text(encoding="utf-8"))
    assert hashlib.sha256(out_opt.with_suffix(".stdout").read_bytes()).hexdigest() == payload["observed"]["raw_stdout_sha256"]

    # 2. Security authority
    out_sec = tmp_path / "security_authority.json"
    subprocess.run(["python3", "scripts/generate_security_authority_primitive.py", "--candidate", candidate, "--output", str(out_sec)], check=True)
    assert out_sec.exists()
    assert out_sec.with_suffix(".stdout").exists()
    payload = json.loads(out_sec.read_text(encoding="utf-8"))
    assert hashlib.sha256(out_sec.with_suffix(".stdout").read_bytes()).hexdigest() == payload["observed"]["raw_stdout_sha256"]

    # 3. Evidence integrity
    manifest = tmp_path / "primitive_manifest.json"
    manifest.write_text(json.dumps({"option_mirror": "option_mirror.json", "security_authority": "security_authority.json"}), encoding="utf-8")
    out_evi = tmp_path / "evidence_integrity.json"
    subprocess.run(["python3", "scripts/generate_evidence_integrity_primitive.py", "--candidate", candidate, "--primitive-root", str(tmp_path), "--output", str(out_evi)], check=True)
    assert out_evi.exists()
    assert out_evi.with_suffix(".stdout").exists()
    payload = json.loads(out_evi.read_text(encoding="utf-8"))
    assert hashlib.sha256(out_evi.with_suffix(".stdout").read_bytes()).hexdigest() == payload["observed"]["raw_stdout_sha256"]
