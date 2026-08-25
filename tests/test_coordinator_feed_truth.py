import time

import pytest

from core.canonical_cycle_coordinator import normalize_feed_truth


def _valid(*, session_id="session", source_sha="a" * 40, ts_epoch=None):
    return (
        {
            "payload": {
                "session_id": session_id,
                "source_sha": source_sha,
                "feed_health_truth": {
                    "context": {"feed_state": "LIVE", "runtime_state": "RUNNING"},
                    "feed_ok": True,
                    "websocket_ok": True,
                },
            }
        },
        {
            "ts_epoch": time.time() if ts_epoch is None else ts_epoch,
            "runtime_state": "RUNNING",
            "feed_truth_state": "LIVE",
            "ws_connected": True,
        },
    )


def test_actual_nested_feed_truth_normalizes():
    value, runtime = _valid()
    normalized = normalize_feed_truth(value, runtime_truth=runtime, expected_session_id="session", expected_source_sha="a" * 40)
    assert normalized["feed_state"] == "LIVE"
    assert normalized["ws_connected"] is True


@pytest.mark.parametrize("mutator, error", [
    (lambda v: v["payload"].pop("feed_health_truth"), "FEED_TRUTH_REQUIRED_WRAPPER_MISSING"),
    (lambda v: v["payload"]["feed_health_truth"]["context"].pop("feed_state"), "FEED_TRUTH_REQUIRED_CONTEXT_FIELD_INVALID"),
    (lambda v: v["payload"]["feed_health_truth"]["feed_ok"].__class__, "unused"),
])
def test_invalid_nested_truth_fails_closed(mutator, error):
    value, runtime = _valid()
    if error == "unused":
        value["payload"]["feed_health_truth"]["feed_ok"] = "true"
        error = "FEED_TRUTH_REQUIRED_FIELD_INVALID"
    else:
        mutator(value)
    with pytest.raises(ValueError, match=error):
        normalize_feed_truth(value, runtime_truth=runtime, expected_session_id="session", expected_source_sha="a" * 40)


def test_stale_session_sha_and_runtime_fail_closed():
    value, runtime = _valid(ts_epoch=time.time() - 30)
    with pytest.raises(ValueError, match="FEED_TRUTH_SESSION_MISMATCH"):
        normalize_feed_truth(value, runtime_truth=runtime, expected_session_id="other", expected_source_sha="a" * 40)
    value, runtime = _valid()
    with pytest.raises(ValueError, match="FEED_TRUTH_SOURCE_SHA_MISMATCH"):
        normalize_feed_truth(value, runtime_truth=runtime, expected_session_id="session", expected_source_sha="b" * 40)
    value, runtime = _valid(ts_epoch=time.time() - 30)
    with pytest.raises(ValueError, match="FEED_TRUTH_RUNTIME_STALE"):
        normalize_feed_truth(value, runtime_truth=runtime, expected_session_id="session", expected_source_sha="a" * 40)


def test_coordinator_admission_shape_is_normalized():
    value, runtime = _valid()
    normalized = normalize_feed_truth(value, runtime_truth=runtime, expected_session_id="session", expected_source_sha="a" * 40)
    assert normalized["feed_state"] == "LIVE"
    assert normalized["runtime_state"] == "RUNNING"
