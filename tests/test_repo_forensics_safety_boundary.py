from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.safety_boundary import audit_safety_boundaries


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
        "def run(client):\n    client.place_order()\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert report.critical
    assert report.critical[0].boundary == "order_action_call"


def test_safety_boundary_flags_readonly_action_fields(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "dashboard" / "report.py",
        "is_order_action = True\nbroker_api_called = True\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    boundaries = {item.boundary for item in report.critical}
    assert "unsafe_action_field" in boundaries


def test_safety_boundary_allows_safe_regular_file(tmp_path):
    _write(tmp_path / "app.py", "def run():\n    return 'ok'\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_safety_boundaries(tmp_path, config)

    assert report.findings == []
