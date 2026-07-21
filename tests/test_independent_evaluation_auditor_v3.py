from __future__ import annotations

import subprocess


def test_auditor_runs_on_pre_open_artifacts():
    result = subprocess.run(["python3", "scripts/audit_independent_underlying_evaluation_v3.py"], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"verdict": "PASS"' in result.stdout

