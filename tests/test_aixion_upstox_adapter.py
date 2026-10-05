from __future__ import annotations

from datetime import datetime, timezone
from aixion_trade_intelligence.adapters.upstox import adapt_upstox_quote_row


def test_upstox_ltp_only_remains_ltp_only():
    event = adapt_upstox_quote_row({"instrument_key": "NSE_EQ|TEST", "receive_wall_ts_utc": "2026-08-04T10:00:00Z", "ltp": 100.0, "bid_price_1": None, "ask_price_1": None}, session_id="s", producer_sequence=1)
    assert event is not None; assert event.data_quality_state == "LTP_ONLY"; assert event.payload["depth_available"] is False; assert event.payload["bid"] is None; assert event.payload["ask"] is None


def test_upstox_epoch_unit_is_derived_from_magnitude():
    seconds = 1785750657.0
    for value in (seconds, seconds * 1_000):
        event = adapt_upstox_quote_row({"instrument_key": "NSE_FO|1", "ts": value, "ltp": 10.0, "bid_price": 9.9, "ask_price": 10.1}, session_id="s", producer_sequence=1, observed_at=datetime.fromtimestamp(seconds, tz=timezone.utc))
        assert event is not None; assert event.event_time == datetime.fromtimestamp(seconds, tz=timezone.utc); assert event.data_quality_state == "TWO_SIDED_QUOTE"


def test_importer_derives_exact_candidate_instruments():
    import uuid
    from scripts.import_upstox_parquet import _derive_candidate_instruments
    from aixion_trade_intelligence.contracts import CanonicalEvent
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    event = CanonicalEvent(event_id=str(uuid.uuid4()), event_type="CANDIDATE_CREATED", session_id="s", source_component="test", producer_id="p", producer_sequence=1, event_time=now, source_time=now, receive_time=now, available_time=now, parse_time=now, persist_time=now, candidate_id="c", strategy_id="strategy", payload={"direction": "BUY_CALL", "underlying_instrument": "NSE_INDEX|Nifty 50", "selected_option_instrument": "NSE_FO|12345", "outcome_contract": {"horizons_seconds": [60], "underlying_instrument": "NSE_INDEX|Nifty 50", "selected_option_instrument": "NSE_FO|12345"}})
    assert _derive_candidate_instruments([event]) == {"NSE_INDEX|Nifty 50", "NSE_FO|12345"}


def test_importer_derives_session_contract_instruments():
    import uuid
    from scripts.import_upstox_parquet import _derive_exact_instruments
    from aixion_trade_intelligence.contracts import CanonicalEvent
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    event = CanonicalEvent(event_id=str(uuid.uuid4()), event_type="SESSION_STARTED", session_id="s", source_component="test", producer_id="p", producer_sequence=1, event_time=now, source_time=now, receive_time=now, available_time=now, parse_time=now, persist_time=now, payload={"analytics_contract": {"index_instrument": "NSE_INDEX|Nifty 50", "futures_instrument": "NSE_FO|FUT", "constituents": [{"instrument_key": "NSE_EQ|AAA", "weight": 1.0}]}})
    assert _derive_exact_instruments([event]) == {"NSE_INDEX|Nifty 50", "NSE_FO|FUT", "NSE_EQ|AAA"}
