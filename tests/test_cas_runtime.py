from datetime import datetime

import pytest

from core.cas_runtime import CASRuntime, DIRECTION_INPUTS_READY, FROZEN, WAITING_FOR_1513
from core.cas_v2_consumer_contract import IST


def runtime():
    return CASRuntime("2026-08-31", "kite-read-only-2026-08-31", "a" * 40, "b" * 40)


def test_capture_persist_recover_and_delayed_freeze(tmp_path):
    r = runtime().capture(input_name="15:10", value=100, market_timestamp=datetime(2026, 8, 31, 15, 10, tzinfo=IST))
    assert r.state == WAITING_FOR_1513
    r.persist(tmp_path / "cas.json")
    r = CASRuntime.recover(tmp_path / "cas.json", session_id=r.session_id, source_sha=r.source_sha, cas_spec_sha=r.cas_spec_sha)
    r = r.capture(input_name="15:13", value=101, market_timestamp=datetime(2026, 8, 31, 15, 13, tzinfo=IST))
    assert r.state == DIRECTION_INPUTS_READY
    r = r.freeze(now=datetime(2026, 8, 31, 15, 14, 2, tzinfo=IST), direction="UP")
    assert r.state == FROZEN and r.decision["direction"] == "UP"
    assert r.freeze(now=datetime(2026, 8, 31, 15, 15, tzinfo=IST), direction="DOWN").decision == r.decision


def test_duplicate_and_future_input_fail_closed(tmp_path):
    r = runtime().capture(input_name="15:10", value=100, market_timestamp=datetime(2026, 8, 31, 15, 10, tzinfo=IST))
    assert r.capture(input_name="15:10", value=999, market_timestamp=datetime(2026, 8, 31, 15, 10, tzinfo=IST)).inputs["15:10"]["value"] == 100
    with pytest.raises(ValueError, match="after_freeze"):
        r.capture(input_name="15:13", value=101, market_timestamp=datetime(2026, 8, 31, 15, 14, tzinfo=IST))
