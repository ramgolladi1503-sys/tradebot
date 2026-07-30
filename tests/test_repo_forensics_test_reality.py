from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.test_reality import classify_tests, score_test_strength


BROKER_FIELD = "broker" + "_api_called"
ORDER_CALL = "place" + "_order"
ASSERT_TEXT = "assert" + " "


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
    _write(
        tmp_path / "tests" / "test_safety.py",
        f"def test_safety():\n    {BROKER_FIELD} = False\n    assert {BROKER_FIELD} is False\n",
    )
    _write(
        tmp_path / "tests" / "test_evidence.py",
        "def test_evidence():\n    record = {'candidate_id': 'x', 'reason': 'blocked'}\n    assert record['reason'] == 'blocked'\n",
    )
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
    assert report.tests[0].strength_grade == "weak"
    assert report.tests[0].strength_score == 0


def test_minerva_strength_scoring_tracks_weak_medium_and_strong_tests(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "tests" / "test_strong_safety.py",
        "def test_blocks_unsafe_path():\n"
        f"    {BROKER_FIELD} = False\n"
        "    is_order_action = False\n"
        f"    assert {BROKER_FIELD} is False\n"
        "    assert is_order_action is False\n"
        "    assert 'unsafe_path' not in {'safe_path'}\n",
    )
    _write(tmp_path / "tests" / "test_medium_behavior.py", "def test_behavior():\n    assert 2 + 2 == 4\n")
    _write(tmp_path / "tests" / "test_weak_unknown.py", "def test_unknown():\n    value = 1\n")
    config = load_config(_write_profile(tmp_path))

    report = classify_tests(tmp_path, config)
    scores = {item.path: (item.strength_score, item.strength_grade) for item in report.tests}

    assert scores["tests/test_strong_safety.py"] == (100, "strong")
    assert scores["tests/test_medium_behavior.py"] == (45, "medium")
    assert scores["tests/test_weak_unknown.py"] == (0, "weak")
    assert report.strength_grade_counts["strong"] == 1
    assert report.strength_grade_counts["medium"] == 1
    assert report.strength_grade_counts["weak"] == 1


def test_score_test_strength_penalizes_fake_confidence_and_mock_only_proof():
    fake_score = score_test_strength(
        test_class="FAKE_CONFIDENCE",
        declared_strength="weak",
        assertion_count=1,
        source="def test_fake():\n    " + ASSERT_TEXT + "result is not None\n",
        risks=[],
    )
    mock_score = score_test_strength(
        test_class="UNIT_BEHAVIOR",
        declared_strength="medium",
        assertion_count=1,
        source=(
            "def test_mock():\n"
            f"    {BROKER_FIELD} = False\n"
            f"    mock_broker.{ORDER_CALL}()\n"
            "    assert response == 'ok'\n"
        ),
        risks=["mock_heavy"],
    )

    assert fake_score.score == 0
    assert fake_score.grade == "weak"
    assert "fake_confidence:-40" in fake_score.reasons
    assert mock_score.score == 35
    assert mock_score.grade == "weak"
    assert "mock_without_negative_proof:-10" in mock_score.reasons


def test_minerva_does_not_treat_fake_assertion_text_inside_fixture_as_executable(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "tests" / "test_auditor_fixture.py",
        "def test_auditor_fixture():\n"
        "    fixture = 'def test_placeholder():\\n    assert True\\n'\n"
        "    findings = ['unconditional_assert_true'] if 'assert True' in fixture else []\n"
        "    assert findings == ['unconditional_assert_true']\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = classify_tests(tmp_path, config)
    status = next(item for item in report.tests if item.path == "tests/test_auditor_fixture.py")

    assert status.test_class != "FAKE_CONFIDENCE"
    assert status.strength_grade in {"medium", "strong"}


def test_minerva_accepts_len_comparison_but_rejects_bare_len_assertion(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "tests" / "test_len_comparison.py",
        "def test_len_comparison():\n    patches = [1, 2]\n    assert len(patches) == 2\n",
    )
    _write(
        tmp_path / "tests" / "test_bare_len.py",
        "def test_bare_len():\n    patches = [1]\n    assert len(patches)\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = classify_tests(tmp_path, config)
    classes = {item.path: item.test_class for item in report.tests}

    assert classes["tests/test_len_comparison.py"] != "FAKE_CONFIDENCE"
    assert classes["tests/test_bare_len.py"] == "FAKE_CONFIDENCE"


def test_minerva_flags_real_unconditional_assert_true(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "tests" / "test_placeholder.py",
        "def test_placeholder():\n    assert True\n",
    )
    config = load_config(_write_profile(tmp_path))

    report = classify_tests(tmp_path, config)

    assert report.tests[0].test_class == "FAKE_CONFIDENCE"
