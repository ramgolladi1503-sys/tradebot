from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.test_reality import classify_tests


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


def test_test_reality_classifier_identifies_core_classes(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "tests" / "test_shape.py", "def test_shape():\n    result = {'score': 1}\n    assert 'score' in result\n")
    _write(tmp_path / "tests" / "test_safety.py", "def test_safety():\n    broker_api_called = False\n    assert broker_api_called is False\n")
    _write(tmp_path / "tests" / "test_evidence.py", "def test_evidence():\n    record = {'candidate_id': 'x', 'reason': 'blocked'}\n    assert record['reason'] == 'blocked'\n")
    _write(tmp_path / "tests" / "test_behavior.py", "def test_behavior():\n    assert 2 + 2 == 4\n")
    config = load_config(_write_profile(tmp_path))

    report = classify_tests(tmp_path, config)
    classes = {item.path: item.test_class for item in report.tests}

    assert classes["tests/test_shape.py"] == "FAKE_CONFIDENCE"
    assert classes["tests/test_safety.py"] == "SAFETY_REGRESSION"
    assert classes["tests/test_evidence.py"] == "EVIDENCE_CONTRACT"
    assert classes["tests/test_behavior.py"] == "UNIT_BEHAVIOR"


def test_test_reality_classifier_marks_no_assertion_test_unknown(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "tests" / "test_unknown.py", "def test_unknown():\n    value = 1\n")
    config = load_config(_write_profile(tmp_path))

    report = classify_tests(tmp_path, config)

    assert report.tests[0].test_class == "UNKNOWN"
    assert report.tests[0].strength == "weak"
