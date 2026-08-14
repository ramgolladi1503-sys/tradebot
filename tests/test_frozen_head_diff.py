from scripts.validate_frozen_head_diff import classify_diff_check


def test_evidence_markdown_eof_formatting_is_non_blocking():
    allowed, blocking = classify_diff_check("docs/review.md:4: new blank line at EOF.")
    assert allowed and not blocking


def test_source_whitespace_remains_blocking():
    allowed, blocking = classify_diff_check("core/feed/runtime.py:4: trailing whitespace.")
    assert blocking and not allowed
