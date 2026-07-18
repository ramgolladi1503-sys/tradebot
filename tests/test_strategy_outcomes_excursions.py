from research.strategy_outcomes.contract import OutcomeBar, OutcomeCandidate
from research.strategy_outcomes.excursions import mfe_mae


def test_mfe_mae_uses_intrabar_extremes():
    candidate = OutcomeCandidate("c", "s", "NIFTY", "BUY_CALL", "2026-01-01T09:15:00+05:30", "s", "c")
    bars = [
        OutcomeBar("2026-01-01T09:15:00+05:30", 100, 100, 100, 100, "s"),
        OutcomeBar("2026-01-01T09:16:00+05:30", 100, 105, 97, 102, "s"),
    ]
    result = mfe_mae(candidate, bars, horizon=1)
    assert result["mfe"] == 0.05
    assert result["mae"] == -0.03
