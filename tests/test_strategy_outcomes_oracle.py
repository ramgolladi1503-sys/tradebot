import pytest

from research.strategy_outcomes.contract import OutcomeBar, OutcomeContractError
from research.strategy_outcomes.oracle import validate_bar_sequence


def test_oracle_rejects_duplicate_timestamp():
    bars = [
        OutcomeBar("t1", 100, 101, 99, 100, "s"),
        OutcomeBar("t1", 100, 101, 99, 100, "s"),
    ]
    with pytest.raises(OutcomeContractError, match="duplicate_source_timestamp") as exc:
        validate_bar_sequence(bars)
    assert str(exc.value) == "duplicate_source_timestamp"


def test_oracle_rejects_mixed_session_before_outcome_measurement():
    bars = [
        OutcomeBar("t1", 100, 101, 99, 100, "s1"),
        OutcomeBar("t2", 100, 101, 99, 100, "s2"),
    ]
    with pytest.raises(OutcomeContractError, match="mixed_session") as exc:
        validate_bar_sequence(bars)
    assert str(exc.value) == "mixed_session"
