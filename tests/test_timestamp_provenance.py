from core.timestamp_provenance import verify_tick_timestamp_provenance

def row(**changes):
    out = {"last_price": 100.0, "timestamp_epoch": 10.0, "timestamp_authority": "EXCHANGE_TIMESTAMP", "timestamp_source_field": "exchange_timestamp", "source_timestamp_epoch": 10.0, "receive_timestamp_epoch": 11.0, "timestamp_fallback_used": False}
    out.update(changes); return out

def test_exchange_and_receive_fallback():
    assert verify_tick_timestamp_provenance(row()) == (True, "ok")
    assert verify_tick_timestamp_provenance(row(timestamp_epoch=11.0, timestamp_authority="GOVERNED_RECEIVE_TIMESTAMP", timestamp_source_field=None, source_timestamp_epoch=None, timestamp_fallback_used=True)) == (True, "ok")

def test_inconsistent_metadata_fails_closed():
    assert verify_tick_timestamp_provenance(row(source_timestamp_epoch=12.0))[0] is False
    assert verify_tick_timestamp_provenance(row(timestamp_authority="BROKER"))[0] is False
