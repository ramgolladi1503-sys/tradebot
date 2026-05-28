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


def test_runtime_wiring_resolves_dotted_function_symbol_without_importing_runtime(tmp_path):
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
  live_startup:
    expected_chain:
      - main.py
      - core.runtime_safety_boot_guard.enforce_runtime_boot_safety
""",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    core = tmp_path / "core"
    core.mkdir()
    (core / "runtime_safety_boot_guard.py").write_text(
        "def enforce_runtime_boot_safety():\n    return None\n",
        encoding="utf-8",
    )
    config = load_config(cfg)

    report = audit_runtime_wiring(tmp_path, config)

    status = report.flow_statuses["live_startup"][1]
    assert status.status == "PASS"
    assert status.evidence == "symbol_defined:core/runtime_safety_boot_guard.py:enforce_runtime_boot_safety"


def test_runtime_wiring_resolves_dotted_class_symbol(tmp_path):
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
  live_startup:
    expected_chain:
      - core.orchestrator.Orchestrator
""",
        encoding="utf-8",
    )
    core = tmp_path / "core"
    core.mkdir()
    (core / "orchestrator.py").write_text(
        "class Orchestrator:\n    pass\n",
        encoding="utf-8",
    )
    config = load_config(cfg)

    report = audit_runtime_wiring(tmp_path, config)

    status = report.flow_statuses["live_startup"][0]
    assert status.status == "PASS"
    assert status.evidence == "symbol_defined:core/orchestrator.py:Orchestrator"


def test_runtime_wiring_reports_missing_symbol_as_failure(tmp_path):
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
  live_startup:
    expected_chain:
      - core.auth.validate_kite_startup_credentials
""",
        encoding="utf-8",
    )
    core = tmp_path / "core"
    core.mkdir()
    (core / "auth.py").write_text("def other_function():\n    return None\n", encoding="utf-8")
    config = load_config(cfg)

    report = audit_runtime_wiring(tmp_path, config)

    status = report.flow_statuses["live_startup"][0]
    assert status.status == "FAIL"
    assert status.evidence == "symbol_missing:core/auth.py:validate_kite_startup_credentials"


def test_runtime_wiring_preserves_shell_entrypoint_file_check(tmp_path):
    cfg = tmp_path / "forensics.yaml"
    cfg.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - run_live.sh
critical_modules:
  runtime:
    - run_live.sh
runtime_flow:
  live_startup:
    expected_chain:
      - run_live.sh
""",
        encoding="utf-8",
    )
    (tmp_path / "run_live.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    config = load_config(cfg)

    report = audit_runtime_wiring(tmp_path, config)

    status = report.flow_statuses["live_startup"][0]
    assert status.status == "PASS"
    assert status.evidence == "file_exists:run_live.sh"
