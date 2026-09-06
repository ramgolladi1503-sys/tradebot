from __future__ import annotations

from datetime import datetime, timezone

from aixion_trade_intelligence.adapters.tradebot import adapt_tradebot_record


def test_adapter_preserves_source_facts_without_inference():
    now = datetime(2026, 8, 4, tzinfo=timezone.utc)
    event = adapt_tradebot_record(
        {
            "timestamp": now.isoformat(),
            "instrument_key": "NSE_INDEX|Nifty 50",
            "ltp": 24500.0,
            "candidate_id": "c-1",
            "strategy_name": "TEST",
        },
        event_type="MARKET_QUOTE",
        session_id="s-1",
        source_component="market_data",
        producer_id="tradebot-market-data",
        producer_sequence=1,
        now=now,
    )
    assert event.payload["ltp"] == 24500.0
    assert "bid" not in event.payload
    assert event.instrument_key == "NSE_INDEX|Nifty 50"
