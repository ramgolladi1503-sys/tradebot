from research.strategy_outcomes.contract import OutcomeBar, OutcomeCandidate
from research.strategy_outcomes.path_events import stop_target_event


def test_same_bar_stop_target_is_ambiguous():
    candidate = OutcomeCandidate("c", "s", "NIFTY", "BUY_CALL", "2026-01-01T09:15:00+05:30", "s", "c")
    bars = [
        OutcomeBar("2026-01-01T09:15:00+05:30", 100, 100, 100, 100, "s"),
        OutcomeBar("2026-01-01T09:16:00+05:30", 100, 103, 97, 101, "s"),
    ]
    assert stop_target_event(candidate, bars, stop_return=0.02, target_return=0.02, horizon=1) == "AMBIGUOUS_SAME_BAR"
