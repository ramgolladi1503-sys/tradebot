from research.strategy_outcomes.contract import OutcomeBar, OutcomeCandidate
from research.strategy_outcomes.forward_returns import forward_returns, legal_entry_index


def test_entry_starts_after_proposal_bar():
    bars = [
        OutcomeBar("2026-01-01T09:15:00+05:30", 100, 101, 99, 100, "s"),
        OutcomeBar("2026-01-01T09:16:00+05:30", 101, 102, 100, 102, "s"),
    ]
    assert legal_entry_index(bars, "2026-01-01T09:15:00+05:30") == 1


def test_forward_return_directional():
    candidate = OutcomeCandidate("c", "s", "NIFTY", "BUY_PUT", "2026-01-01T09:15:00+05:30", "s", "c")
    bars = [
        OutcomeBar("2026-01-01T09:15:00+05:30", 100, 101, 99, 100, "s"),
        OutcomeBar("2026-01-01T09:16:00+05:30", 100, 101, 99, 100, "s"),
        OutcomeBar("2026-01-01T09:17:00+05:30", 100, 101, 98, 98, "s"),
    ]
    assert forward_returns(candidate, bars, horizons=(1,))["1"] == 0.02
