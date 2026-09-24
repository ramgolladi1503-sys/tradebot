from datetime import datetime, timezone, timedelta
import hashlib
from pathlib import Path
from core.cas_morning_reversal_advisory import SPEC_SHA, evaluate


SOURCE_SHA = "1" * 40

def test_sign_semantics_and_safety():
    spec_path = Path(__file__).parents[1] / "research/cas/morning_reversal_short_horizon_v1/CAS_MORNING_REVERSAL_SHORT_HORIZON_SPEC_V1.json"
    assert hashlib.sha256(spec_path.read_bytes()).hexdigest() == SPEC_SHA
    t = datetime(2026, 9, 1, 9, 44, tzinfo=timezone.utc)
    assert evaluate(session_id="s", symbol="NIFTY", morning_return=1, observation_timestamp=t, cutoff_timestamp=t, source_sha=SOURCE_SHA)["direction"] == "DOWN"
    assert evaluate(session_id="s", symbol="NIFTY", morning_return=-1, observation_timestamp=t, cutoff_timestamp=t, source_sha=SOURCE_SHA)["direction"] == "UP"
    row = evaluate(session_id="s", symbol="NIFTY", morning_return=0, observation_timestamp=t, cutoff_timestamp=t, source_sha=SOURCE_SHA)
    assert row["direction"] == "NO_SIGNAL" and row["live_execution_authorized"] is False
    assert row["option_side"] is None and row["prospective_target_session_count"] == 20
    assert row["spec_sha"] == SPEC_SHA and len(row["spec_sha"]) == 64
    assert row["strategy_id"] == "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"

def test_cutoff_and_lag_fail_closed():
    cutoff = datetime(2026, 9, 1, 9, 44, tzinfo=timezone.utc)
    for kwargs, error in [({"observation_timestamp": cutoff - timedelta(seconds=1)}, "pre_cutoff_observation"), ({"observation_timestamp": cutoff, "received_timestamp": cutoff + timedelta(milliseconds=2001)}, "observation_late")]:
        try:
            evaluate(session_id="s", symbol="NIFTY", morning_return=1, source_sha=SOURCE_SHA, cutoff_timestamp=cutoff, **kwargs)
            assert False
        except ValueError as exc:
            assert str(exc) == error


def test_invalid_strategy_identity_and_nonfinite_return_fail_closed():
    t = datetime(2026, 9, 1, 9, 44, tzinfo=timezone.utc)
    for kwargs, error in [
        ({"session_id": "s", "symbol": "BANKNIFTY", "morning_return": 1, "source_sha": SOURCE_SHA}, "strategy_identity_invalid"),
        ({"session_id": "s", "symbol": "NIFTY", "morning_return": float("nan"), "source_sha": SOURCE_SHA}, "morning_return_invalid"),
    ]:
        try:
            evaluate(observation_timestamp=t, cutoff_timestamp=t, **kwargs)
            assert False
        except ValueError as exc:
            assert str(exc) == error
