from __future__ import annotations

import subprocess

from tools.code_excellence.cerberus_gate import run_cerberus_gate


def test_unchanged_baseline_marker_is_not_reported(tmp_path, monkeypatch):
    marker = "restricted_" + "call"
    config = tmp_path / ".gsd-forensics.yaml"
    config.write_text(
        f"""
agent_parameters:
  cerberus:
    protected_modes: [SIM]
    forbidden_import_markers: [{marker}]
    required_non_action_fields: []
    output_required: [boundary_status]
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    target = tmp_path / "adapter.py"
    target.write_text(f"def {marker}():\n    return None\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True)
    target.write_text(f"def {marker}():\n    return None\nSAFE = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "candidate"], cwd=tmp_path, check=True)
    monkeypatch.setenv("CERBERUS_BASE_REF", "HEAD~1")
    monkeypatch.setenv("CERBERUS_CANDIDATE_REF", "HEAD")
    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("adapter.py",),
    )
    assert report.block_count == 0
