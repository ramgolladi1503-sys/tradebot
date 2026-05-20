from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.product_reality import audit_product_reality


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
  product_reality:
    capabilities:
      - candidate ranking
      - live broker execution
      - replay validation
      - option pressure edge
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


def _status(report, capability):
    return {item.capability: item for item in report.capabilities}[capability]


def test_product_reality_classifies_proven_capability(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "core" / "candidate_ranking.py", "def rank_candidate():\n    return 'candidate ranking'\n")
    _write(tmp_path / "tests" / "test_candidate_ranking.py", "def test_candidate_ranking():\n    assert 'candidate ranking'\n")
    _write(tmp_path / "docs" / "candidate_ranking_evidence.md", "candidate ranking evidence\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_product_reality(tmp_path, config)

    item = _status(report, "candidate ranking")
    assert item.status == "PROVEN"
    assert item.proof_files
    assert item.test_files
    assert item.evidence_files


def test_product_reality_classifies_mocked_capability(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "tests" / "test_live_broker_execution.py", "def test_live_broker_execution_mock():\n    mock_live_broker_execution = True\n    assert mock_live_broker_execution\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_product_reality(tmp_path, config)

    item = _status(report, "live broker execution")
    assert item.status == "MOCKED"
    assert item.test_files


def test_product_reality_classifies_theoretical_capability(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "docs" / "replay_validation.md", "replay validation future placeholder\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_product_reality(tmp_path, config)

    item = _status(report, "replay validation")
    assert item.status == "THEORETICAL"
    assert item.evidence_files


def test_product_reality_classifies_unproven_capability(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_product_reality(tmp_path, config)

    item = _status(report, "option pressure edge")
    assert item.status == "UNPROVEN"
