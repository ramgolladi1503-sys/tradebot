from scripts.validate_runtime_authority_scope import classify_scope
from scripts.validate_agent_review_evidence import _candidate_file_text, _missing_sections


def test_unrelated_high_risk_change_without_focused_tests_fails_contract():
    classification, paths = classify_scope(["core/feed/runtime_store.py", "README.md"])
    assert classification == "UNAUTHORIZED_HIGH_RISK_CHANGE"
    assert paths == ["core/feed/runtime_store.py"]


def test_governed_high_risk_change_with_focused_tests_is_eligible():
    classification, paths = classify_scope(
        ["core/feed/runtime_store.py", "tests/test_feed_artifact_loader.py"]
    )
    assert classification == "AUTHORIZED_GOVERNED_HIGH_RISK_CHANGE_WITH_EVIDENCE"
    assert paths == ["core/feed/runtime_store.py"]


def test_non_high_risk_change_is_not_rejected():
    assert classify_scope(["docs/notes.md"])[0] == "NO_HIGH_RISK_CHANGES"


def test_review_contract_still_requires_all_sections():
    missing = _missing_sections("Agent Work Contract\nScope Guard\nHigh-Risk Path Review")
    assert "Human Approval" in missing
    assert "High-Risk Path Review" not in missing


def test_agent_review_text_can_be_read_from_candidate_git_tree(monkeypatch, tmp_path):
    path = tmp_path / "docs" / "agent_reviews" / "review.md"

    class Result:
        returncode = 0
        stdout = "## High-Risk Path Review\n"
        stderr = ""

    monkeypatch.setattr(
        "scripts.validate_agent_review_evidence.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    assert _candidate_file_text("HEAD", path) == "## High-Risk Path Review\n"


def test_agent_review_text_prefers_committed_candidate_blob(monkeypatch, tmp_path):
    path = tmp_path / "review.md"
    path.write_text("stale checkout text", encoding="utf-8")

    class Result:
        returncode = 0
        stdout = "committed candidate text"
        stderr = ""

    monkeypatch.setattr(
        "scripts.validate_agent_review_evidence.subprocess.run",
        lambda *args, **kwargs: Result(),
    )

    assert _candidate_file_text("HEAD", path) == "committed candidate text"
