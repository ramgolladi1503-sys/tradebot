from __future__ import annotations

from pathlib import Path

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.runtime_wiring import audit_runtime_wiring


def test_runtime_wiring_audit_uses_configured_tradebot_flows():
    repo_root = Path(__file__).resolve().parents[1]
    config = load_config(repo_root / ".gsd-forensics.yaml")

    report = audit_runtime_wiring(repo_root, config)

    assert "live_startup" in report.flow_statuses
    assert "candidate_to_decision" in report.flow_statuses
    live_steps = {item.step: item for item in report.flow_statuses["live_startup"]}
    assert live_steps["run_live.sh"].status == "PASS"
    assert live_steps["main.py"].status == "PASS"


def test_runtime_wiring_report_marks_missing_module_as_failure(tmp_path):
    cfg = tmp_path / "forensics.yaml"
    cfg.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - main.py
critical_modules:
  runtime:
    - main.py
runtime_flow:
  sample:
    expected_chain:
      - main.py
      - core.missing_runtime.module
""",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    config = load_config(cfg)

    report = audit_runtime_wiring(tmp_path, config)

    assert report.flow_statuses["sample"][0].status == "PASS"
    assert report.flow_statuses["sample"][1].status == "FAIL"
    assert "module_file_missing" in report.flow_statuses["sample"][1].evidence
