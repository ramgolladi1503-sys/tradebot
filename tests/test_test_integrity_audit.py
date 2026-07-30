from pathlib import Path

from scripts.audit_test_integrity import audit_file, run_audit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_changed_fake_and_disabled_tests_are_blocking(tmp_path):
    test_file = _write(
        tmp_path / "tests" / "test_bad_evidence.py",
        """
import pytest


def test_unconditional():
    assert True


@pytest.mark.skip(reason="not implemented")
def test_disabled():
    assert 1 == 1


def test_empty():
    pass
""",
    )

    report = run_audit(
        [tmp_path / "tests"],
        changed_paths={test_file.as_posix()},
    )

    kinds = {finding["kind"] for finding in report["findings"]}
    assert "unconditional_assert_true" in kinds
    assert "skipped_test" in kinds
    assert "empty_test" in kinds
    assert report["blocking_count"] == 3


def test_legacy_weak_test_is_reported_without_blocking_new_work(tmp_path):
    test_file = _write(
        tmp_path / "tests" / "test_legacy.py",
        """
def test_legacy_placeholder():
    assert True
""",
    )

    report = run_audit([tmp_path / "tests"], changed_paths=set())

    assert report["blocking_count"] == 0
    finding = next(
        item
        for item in report["findings"]
        if item["kind"] == "unconditional_assert_true"
    )
    assert finding["path"] == test_file.as_posix()
    assert finding["severity"] == "warning"
    assert finding["changed"] is False


def test_real_assertion_is_accepted_as_local_oracle(tmp_path):
    test_file = _write(
        tmp_path / "tests" / "test_real.py",
        """
def test_real_behavior():
    actual = 2 + 2
    assert actual == 4
""",
    )

    findings, parse_error = audit_file(test_file, changed=True)

    assert parse_error is None
    assert findings == []


def test_pytest_raises_is_accepted_as_local_oracle(tmp_path):
    test_file = _write(
        tmp_path / "tests" / "test_exception.py",
        """
import pytest


def test_expected_error():
    with pytest.raises(ValueError):
        raise ValueError("expected")
""",
    )

    findings, parse_error = audit_file(test_file, changed=True)

    assert parse_error is None
    assert findings == []


def test_no_local_oracle_is_review_finding_not_automatic_failure(tmp_path):
    test_file = _write(
        tmp_path / "tests" / "test_helper_oracle.py",
        """
def verify_external_contract():
    return None


def test_delegated_oracle():
    verify_external_contract()
""",
    )

    findings, parse_error = audit_file(test_file, changed=True)

    assert parse_error is None
    assert len(findings) == 1
    assert findings[0].kind == "no_local_oracle_detected"
    assert findings[0].severity == "review"


def test_changed_unparseable_test_file_is_blocking(tmp_path):
    test_file = _write(
        tmp_path / "tests" / "test_syntax_error.py",
        "def test_broken(:\n    pass\n",
    )

    report = run_audit(
        [tmp_path / "tests"],
        changed_paths={test_file.as_posix()},
    )

    assert report["blocking_count"] == 1
    assert report["findings"][0]["kind"] == "unparseable_test_file"
