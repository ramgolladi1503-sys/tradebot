from __future__ import annotations

from tools.repo_forensics.architecture_drift import detect_architecture_drift
from tools.repo_forensics.config_loader import load_config


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
agent_parameters:
  architecture_drift:
    watch_areas:
      - ranking
      - risk
      - evidence
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


def test_architecture_drift_detects_duplicate_watch_area_modules(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "core" / "ranking.py", "x = 1\n")
    _write(tmp_path / "strategies" / "ranking.py", "x = 1\n")
    config = load_config(_write_profile(tmp_path))

    report = detect_architecture_drift(tmp_path, config)

    assert any(item.drift_type == "duplicate_module_stem" for item in report.medium)


def test_architecture_drift_detects_old_new_pipeline_split(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "core" / "legacy_ranking.py", "x = 1\n")
    _write(tmp_path / "core" / "ranking_v2.py", "x = 1\n")
    config = load_config(_write_profile(tmp_path))

    report = detect_architecture_drift(tmp_path, config)

    assert any(item.drift_type == "old_new_pipeline_split" for item in report.medium)


def test_architecture_drift_detects_dashboard_evidence_reader_without_configured_path(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "dashboard" / "reader.py", "import json\ndef load():\n    return json.loads('{}')\n")
    config = load_config(_write_profile(tmp_path))

    report = detect_architecture_drift(tmp_path, config)

    assert any(item.drift_type == "dashboard_evidence_reader_unproven" for item in report.unknown)
