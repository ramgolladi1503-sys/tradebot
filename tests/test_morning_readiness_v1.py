import pytest

from core.morning_readiness_v1 import MorningReadiness, MorningState
from scripts.morning_readiness_dry_run import normal_path


def test_normal_path_reaches_preopen_armed():
    assert normal_path().state is MorningState.PREOPEN_ARMED


def test_non_fatal_option_failure_preserves_observation():
    live = normal_path().transition(MorningState.WAITING_FOR_MARKET).transition(MorningState.LIVE_FEED_PENDING).transition(MorningState.LIVE_RUNNING)
    assert live.degraded_for("NO_LIVE_OPTION_FEED").state is MorningState.LIVE_DEGRADED


def test_fatal_storage_failure_fails_closed():
    live = normal_path().transition(MorningState.WAITING_FOR_MARKET).transition(MorningState.LIVE_FEED_PENDING).transition(MorningState.LIVE_RUNNING)
    assert live.degraded_for("WRONG_STORAGE_AUTHORITY").state is MorningState.FAIL_CLOSED


def test_invalid_transition_fails_closed():
    with pytest.raises(ValueError, match="invalid_morning_transition"):
        MorningReadiness().transition(MorningState.LIVE_RUNNING)


def test_authority_escalation_is_rejected():
    state = MorningReadiness(safety={"broker_write_authority": True})
    with pytest.raises(ValueError, match="authority_escalation"):
        state.transition(MorningState.OFFLINE_CERTIFIED)
