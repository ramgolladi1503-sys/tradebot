from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.safety_boundary import audit_safety_boundaries


BROKER_FIELD = "broker" + "_api_called"
ORDER_CALL = "place" + "_order"
KITE_CLIENT = "core." + "kite_client"
KITE_CLIENT_PATH = "core/" + "kite_client.py"


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

    assert report.critical
    assert report.critical[0].boundary == "order_action_call"


def test_safety_boundary_flags_readonly_action_fields(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "dashboard" / "report.py",
        f"is_order_action = True\n{BROKER_FIELD} = True\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    boundaries = {item.boundary for item in report.critical}
    assert "unsafe_action_field" in boundaries


def test_safety_boundary_flags_readonly_import_of_broker_client(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / KITE_CLIENT_PATH, "class KiteClient:\n    pass\n")
    _write(tmp_path / "reports" / "readonly_report.py", f"import {KITE_CLIENT}\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert [item.boundary for item in report.high] == ["readonly_execution_import"]


def test_safety_boundary_flags_paper_path_to_broker_order_call_graph(tmp_path):
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

    boundaries = {item.boundary for item in report.critical}
    assert "paper_sim_broker_import" in boundaries
    assert "paper_sim_live_broker_call_path" in boundaries


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
