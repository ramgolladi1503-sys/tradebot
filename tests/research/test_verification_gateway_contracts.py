"""Synthetic-only fidelity-gateway regression tests; never reads real outcomes."""
from datetime import datetime, timezone, timedelta

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from research.verification_gateway.contracts import (
    ResearchStrategySpec, check_causality, verify_strategy_spec,
)


def valid_payload():
    return {
        "research_id": "synthetic_ema",
        "source_uri_or_artifact_id": "fixture://example",
        "source_digest_sha256": "a" * 64,
        "rules": [{
            "rule_id": "r1", "source_locator": "synthetic fixture line 1",
            "exact_source_text_or_equation": "EMA(13) crosses above EMA(48)",
            "interpretation": "closed bar cross", "is_author_rule": True,
        }],
        "indicator_equations": ["EMA recurrence explicitly defined in real spec"],
        "instrument_and_contract_rule": "synthetic single contract",
        "entry_rule": "after complete signal bar at next available quote",
        "exit_rule": "synthetic fixed timeout",
        "costs_and_fill_convention": "synthetic quotes with explicit fee schedule",
        "required_input_fields": ["event_time", "available_time", "close"],
        "timing": {
            "timezone": "Asia/Kolkata",
            "signal_requires_complete_bar": True,
            "earliest_entry_policy": "NEXT_AVAILABLE_QUOTE",
            "data_available_at": "bar completion",
        },
        "source_review_status": "REVIEW_REQUIRED",
    }


def test_unreviewed_source_never_verified():
    spec = ResearchStrategySpec.model_validate(valid_payload())
    report = verify_strategy_spec(spec, reference_comparison_passed=True,
                                  causal_checks_passed=True, data_checks_passed=True)
    assert not report.translation_verified
    assert "SOURCE_REVIEW_NOT_VERIFIED" in report.issues


def test_reviewed_requires_proof():
    payload = valid_payload()
    payload["source_review_status"] = "INDEPENDENTLY_REVIEWED"
    with pytest.raises(ValidationError):
        ResearchStrategySpec.model_validate(payload)


def test_assumed_rule_requires_rationale():
    payload = valid_payload()
    payload["rules"][0]["is_author_rule"] = False
    with pytest.raises(ValidationError):
        ResearchStrategySpec.model_validate(payload)


def test_content_digest_stable():
    a = ResearchStrategySpec.model_validate(valid_payload())
    b = ResearchStrategySpec.model_validate(valid_payload())
    assert a.content_digest() == b.content_digest()


def test_known_causal_failure():
    z = timezone.utc
    data = datetime(2026, 9, 27, 15, 30, tzinfo=z)
    decision = datetime(2026, 9, 27, 15, 20, tzinfo=z)
    entry = datetime(2026, 9, 27, 15, 20, tzinfo=z)
    assert "FUTURE_DATA_USED" in check_causality(
        data_available=data, signal_decision=decision, first_permitted_entry=entry
    )


@given(st.integers(min_value=1, max_value=3600))
def test_future_availability_always_blocked(seconds):
    now = datetime(2026, 9, 27, 9, 20, tzinfo=timezone.utc)
    issues = check_causality(data_available=now + timedelta(seconds=seconds),
                             signal_decision=now, first_permitted_entry=now)
    assert "FUTURE_DATA_USED" in issues


def test_entry_before_decision_blocked():
    z = timezone.utc
    now = datetime(2026, 9, 27, 9, 20, tzinfo=z)
    assert "ENTRY_BEFORE_DECISION" in check_causality(
        data_available=now, signal_decision=now,
        first_permitted_entry=now - timedelta(seconds=1),
    )
