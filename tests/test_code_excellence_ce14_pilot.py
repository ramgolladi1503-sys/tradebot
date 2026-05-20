from __future__ import annotations

from pathlib import Path


CE12_REVIEW = Path("docs/agent_reviews/CE_12_PR_EVIDENCE_PACK_GENERATOR.md")
REQUIRED_EVIDENCE_FIELDS = (
    "mode:",
    "candidate_id:",
    "decision:",
    "reason:",
    "timestamp:",
    "is_order_action:",
    "broker_api_called:",
    "source:",
)


def test_ce14_pilot_target_has_evidence_contract_header():
    text = CE12_REVIEW.read_text(encoding="utf-8")
    header = text.split("## Purpose", 1)[0]

    for field in REQUIRED_EVIDENCE_FIELDS:
        assert field in header


def test_ce14_pilot_preserves_non_action_evidence():
    text = CE12_REVIEW.read_text(encoding="utf-8")
    header = text.split("## Purpose", 1)[0].lower()

    assert "is_order_action: false" in header
    assert "broker_api_called: false" in header


def test_ce14_pilot_keeps_original_scope_content():
    text = CE12_REVIEW.read_text(encoding="utf-8")

    assert "## Purpose" in text
    assert "## Files Changed" in text
    assert "tools/code_excellence/pr_evidence_pack.py" in text
    assert "## Next PR" in text
