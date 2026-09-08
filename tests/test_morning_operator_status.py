from core.morning_operator_status import build_status


def test_status_is_compact_and_authority_false():
    status = build_status(state="PREOPEN_ARMED", release_sha="a" * 40, cas="ARMED")
    assert status["status"] == "MROS_STATUS"
    assert status["cas"] == "ARMED"
    assert status["broker_write_authority"] is False
    assert status["order_authority"] is False
    assert status["orders_placed"] == 0
