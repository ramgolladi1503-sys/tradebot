from __future__ import annotations

import pytest

from tools.repo_forensics.config_loader import ConfigError, load_config, parse_simple_yaml


def test_parse_simple_yaml_supports_tradebot_profile_shape():
    data = parse_simple_yaml(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - run_live.sh
    - main.py
critical_modules:
  runtime:
    - core/orchestrator.py
"""
    )

    assert data["project"]["name"] == "tradebot"
    assert data["baseline_rules"]["unknown_is_not_pass"] is True
    assert data["entrypoints"]["required"] == ["run_live.sh", "main.py"]
    assert data["critical_modules"]["runtime"] == ["core/orchestrator.py"]


def test_load_config_rejects_missing_required_entrypoints(tmp_path):
    cfg = tmp_path / "forensics.yaml"
    cfg.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  optional:
    - dashboard/streamlit_app.py
critical_modules:
  runtime:
    - core/orchestrator.py
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="entrypoints.required_must_not_be_empty"):
        load_config(cfg)


def test_load_config_exposes_entrypoints_and_critical_modules(tmp_path):
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
  optional:
    - dashboard/streamlit_app.py
critical_modules:
  runtime:
    - main.py
exclude:
  directories:
    - cache_dir
  file_patterns:
    - "*.pyc"
""",
        encoding="utf-8",
    )

    loaded = load_config(cfg)

    assert loaded.required_entrypoints == ["run_live.sh"]
    assert loaded.optional_entrypoints == ["dashboard/streamlit_app.py"]
    assert loaded.critical_modules == {"runtime": ["main.py"]}
    assert "cache_dir" in loaded.excluded_directories
    assert "*.pyc" in loaded.excluded_file_patterns
