import pytest

from research.global_v1.extended_research import ExtendedDecision, ExtendedHypothesis, decide


def hypothesis(predeclared=True):
    return ExtendedHypothesis("h1", "USDINR", "predeclared macro rationale", predeclared, "v" * 64)


def test_missing_data_is_blocked():
    assert decide(hypothesis(), evidence_available=False, incremental_support=None) is ExtendedDecision.BLOCKED_DATA


def test_keep_or_discard_does_not_mutate_v1():
    assert decide(hypothesis(), evidence_available=True, incremental_support=True) is ExtendedDecision.KEEP
    assert decide(hypothesis(), evidence_available=True, incremental_support=False) is ExtendedDecision.DISCARD


def test_unpredeclared_hypothesis_is_rejected():
    with pytest.raises(ValueError, match="PREDECLARED"):
        decide(hypothesis(False), evidence_available=True, incremental_support=True)
