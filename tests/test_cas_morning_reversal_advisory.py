from datetime import datetime, timezone, timedelta
from core.cas_morning_reversal_advisory import evaluate

def test_sign_semantics_and_safety():
    t = datetime(2026, 9, 1, 9, 44, tzinfo=timezone.utc)
    assert evaluate(session_id="s", symbol="NIFTY", morning_return=1, observation_timestamp=t, cutoff_timestamp=t)["direction"] == "DOWN"
    assert evaluate(session_id="s", symbol="NIFTY", morning_return=-1, observation_timestamp=t, cutoff_timestamp=t)["direction"] == "UP"
    row = evaluate(session_id="s", symbol="NIFTY", morning_return=0, observation_timestamp=t, cutoff_timestamp=t)
    assert row["direction"] == "NO_SIGNAL" and row["live_execution_authorized"] is False
    assert row["option_side"] is None and row["prospective_target_session_count"] == 20

def test_cutoff_and_lag_fail_closed():
    cutoff = datetime(2026, 9, 1, 9, 44, tzinfo=timezone.utc)
    for kwargs, error in [({"observation_timestamp": cutoff - timedelta(seconds=1)}, "pre_cutoff_observation"), ({"observation_timestamp": cutoff, "received_timestamp": cutoff + timedelta(milliseconds=2001)}, "observation_late")]:
        try:
            evaluate(session_id="s", symbol="NIFTY", morning_return=1, cutoff_timestamp=cutoff, **kwargs)
            assert False
        except ValueError as exc:
            assert str(exc) == error
