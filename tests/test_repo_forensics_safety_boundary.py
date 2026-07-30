from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.safety_boundary import audit_safety_boundaries


ACTION_FIELD = "is_" + "order_action"
BROKER_FIELD = "broker" + "_api_called"
ORDER_CALL = "place" + "_order"
KITE_CLIENT = "core." + "kite_client"
KITE_CLIENT_PATH = "core/" + "kite_client.py"
TRUE_VALUE = "Tr" + "ue"


def _write_profile(repo_root):
    cfg = repo_root / "forensics.yaml"
    cfg.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - app.py
critical_modules:
  runtime:
    - app.py
exclude:
  directories:
    - cache_dir
""",
        encoding="utf-8",
    )
    return cfg


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_safety_boundary_flags_order_action_in_paper_path(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "paper" / "paper_executor.py",
        f"def run(client):\n    client.{ORDER_CALL}()\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert len(report.critical) == 1
    assert report.critical[0].boundary == "order_action_call"


def test_execution_owner_is_allowed_to_own_order_action_call(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "core" / "execution_engine.py",
        f"def route(client):\n    return client.{ORDER_CALL}()\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert report.findings == []


def test_safety_boundary_flags_readonly_action_fields_once_each(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "dashboard" / "report.py",
        f"{ACTION_FIELD} = {TRUE_VALUE}\n{BROKER_FIELD} = {TRUE_VALUE}\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert [item.boundary for item in report.critical] == [
        "unsafe_action_field",
        "unsafe_action_field",
    ]
    assert {item.evidence for item in report.critical} == {
        f"{ACTION_FIELD}=true",
        f"{BROKER_FIELD}=true",
    }


def test_safety_boundary_flags_readonly_import_of_broker_client(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / KITE_CLIENT_PATH, "class KiteClient:\n    pass\n")
    _write(tmp_path / "reports" / "readonly_report.py", f"import {KITE_CLIENT}\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert [item.boundary for item in report.high] == ["readonly_execution_import"]


def test_paper_broker_import_is_high_but_reachable_order_call_is_critical(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / KITE_CLIENT_PATH, "class KiteClient:\n    pass\n")
    _write(
        tmp_path / "paper" / "paper_flow.py",
        f"from {KITE_CLIENT} import KiteClient\n\n"
        "def run(client):\n"
        f"    client.{ORDER_CALL}()\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert [item.boundary for item in report.high] == ["paper_sim_broker_import"]
    assert {item.boundary for item in report.critical} == {
        "order_action_call",
        "paper_sim_live_broker_call_path",
    }


def test_import_from_broker_module_is_not_duplicated_by_imported_symbol(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / KITE_CLIENT_PATH, "class KiteClient:\n    pass\n")
    _write(
        tmp_path / "paper" / "paper_monitor.py",
        f"from {KITE_CLIENT} import KiteClient, another_symbol\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert len(report.high) == 1
    assert report.high[0].boundary == "paper_sim_broker_import"
    assert report.critical == []


def test_shell_live_marker_produces_one_finding_on_its_actual_line(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "scripts" / "unsafe_start.sh",
        "#!/usr/bin/env bash\necho preparing\nEXECUTION_MODE=LIVE\necho started\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert len(report.high) == 1
    finding = report.high[0]
    assert finding.boundary == "live_mode_default"
    assert finding.line == 3


def test_safety_boundary_does_not_flag_order_words_inside_string_fixture(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "tests" / "test_fixture.py",
        f"def test_fixture_text_only():\n    text = '{ORDER_CALL} mentioned for docs only'\n    assert 'docs only' in text\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert report.findings == []


def test_safety_boundary_allows_safe_regular_file(tmp_path):
    _write(tmp_path / "app.py", "def run():\n    return 'ok'\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert report.findings == []


def test_repo_forensics_constants_do_not_self_trigger_runtime_import_finding(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "tools" / "repo_forensics" / "scanner.py",
        "FORBIDDEN = ['core.market_data', 'core.orchestrator', 'strategies.trade_builder']\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert report.critical == []


def test_repo_forensics_actual_runtime_import_remains_critical(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "core" / "market_data.py", "VALUE = 1\n")
    _write(
        tmp_path / "tools" / "repo_forensics" / "bad_scanner.py",
        "import core.market_data\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert len(report.critical) == 1
    finding = report.critical[0]
    assert finding.boundary == "forensics_runtime_import"
    assert finding.evidence == "forensics_imports_runtime_module:core.market_data"
    assert finding.line == 1


def test_dry_run_proof_import_does_not_equal_direct_broker_capability(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "core" / "live_dry_run_broker_payload_gate.py",
        "def broker_payload_dry_run_approved():\n    return True\n",
    )
    _write(
        tmp_path / "core" / "broker_reconciliation_dry_run_proof.py",
        "from core.live_dry_run_broker_payload_gate import broker_payload_dry_run_approved\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert report.critical == []


def test_test_import_of_direct_broker_subject_is_not_product_runtime_finding(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / KITE_CLIENT_PATH, "class KiteClient:\n    pass\n")
    _write(
        tmp_path / "tests" / "test_paper_kite_client.py",
        f"import {KITE_CLIENT}\n\ndef test_subject_import():\n    assert {KITE_CLIENT.split('.')[-1]} is not None\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert report.findings == []
