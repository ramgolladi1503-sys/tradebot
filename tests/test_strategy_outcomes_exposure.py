from research.strategy_outcomes.contract import OutcomeCandidate
from research.strategy_outcomes.exposure import duplicate_directional_exposure


def test_duplicate_directional_exposure_is_reported():
    c = OutcomeCandidate("c", "s", "NIFTY", "BUY_CALL", "t", "s", "c")
    assert duplicate_directional_exposure([c, c]) == ("s:NIFTY:BUY_CALL:t",)
