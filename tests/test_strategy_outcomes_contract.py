import pytest

from research.strategy_outcomes.contract import OutcomeCandidate, OutcomeContractError


def test_candidate_requires_supported_direction():
    with pytest.raises(OutcomeContractError):
        OutcomeCandidate("c1", "s1", "NIFTY", "BUY_STOCK", "2026-01-01T09:16:00+05:30", "s", "c")


def test_candidate_hash_is_deterministic():
    candidate = OutcomeCandidate("c1", "s1", "NIFTY", "BUY_CALL", "2026-01-01T09:16:00+05:30", "s", "c")
    assert candidate.canonical_hash() == candidate.canonical_hash()
