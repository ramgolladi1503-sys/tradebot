"""End-to-end primitive proof smoke test for PR #905.

Runs proof generation and independent verification in separate subprocesses so
broker-write guards and method spies cannot leak into the pytest process.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_pr905_primitive_proof_and_independent_verifier(tmp_path: Path):
    evidence_root = tmp_path / "pr905-proof"

    generator = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_pr905_canonical_proof.py"),
            "--output-dir",
            str(evidence_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert generator.returncode == 0, generator.stdout + "\n" + generator.stderr

    verifier = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify_pr905_implementation.py"),
            "--evidence-root",
            str(evidence_root),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert verifier.returncode == 0, verifier.stdout + "\n" + verifier.stderr

    payload = json.loads(verifier.stdout)
    assert payload["overall_status"] == "PASS"
    assert payload["codebase_verified"] is True
    assert payload["evidence_verified"] is True
    derived = payload["evidence_report"]["derived"]
    assert derived["future_leak_status"] == "PASS"
    assert derived["broker_write_calls_total"] == 0
    assert derived["execution_router_call_count"] == 0
    assert derived["candidate_selection_authority_count"] == 1
    assert derived["deterministic_replay"] is True

    assert not (evidence_root / "PR905_IMPLEMENTATION_VERIFICATION.json").exists()
