import datetime as dt

from core.feed.tick_utils import (
    best_price,
    coerce_epoch,
    depth_has_bid_ask,
    initial_freshness_epoch,
    normalized_tick_epoch,
    safe_float,
    tick_epoch,
)


def test_epoch_helpers_normalize_tick_timestamps():
    stamp = dt.datetime(2026, 5, 27, 9, 15, tzinfo=dt.timezone.utc)

    assert coerce_epoch(None) is None
    assert coerce_epoch("1700000000") == 1700000000.0
    assert coerce_epoch(1700000000000) == 1700000000.0
    assert tick_epoch({"exchange_timestamp": stamp, "last_trade_time": 1700000001}) == stamp.timestamp()
    assert tick_epoch({"last_trade_time": 1700000001000}) == 1700000001.0
    assert tick_epoch({}, fallback_epoch=1700000002.0) == 1700000002.0


def test_price_and_depth_helpers_fail_closed():
    assert safe_float(None) is None
    assert safe_float("10.25") == 10.25
    assert best_price([]) is None
    assert best_price([{"price": "101.5"}]) == 101.5
    assert depth_has_bid_ask(None) is False
    assert depth_has_bid_ask({"buy": [{"price": 0}], "sell": [{"price": 101}]}) is False
    assert depth_has_bid_ask({"buy": [{"price": 100}], "sell": [{"price": 101}]}) is True


def test_freshness_helpers_are_policy_driven_and_monotonic():
    assert initial_freshness_epoch(
        payload_epoch=100.0,
        receipt_epoch=105.0,
        use_receipt_time_for_options=True,
        is_underlying_token=False,
    ) == 105.0
    assert initial_freshness_epoch(
        payload_epoch=100.0,
        receipt_epoch=105.0,
        use_receipt_time_for_options=True,
        is_underlying_token=True,
    ) == 100.0
    assert normalized_tick_epoch(
        payload_epoch=None,
        receipt_epoch=105.0,
        market_open_now=True,
        is_underlying_token=True,
    ) == 105.0
    assert normalized_tick_epoch(
        payload_epoch=100.0,
        receipt_epoch=105.0,
        previous_epoch=101.0,
        market_open_now=True,
        max_payload_lag_sec=2.0,
        use_receipt_time_for_options=False,
        is_underlying_token=True,
    ) == 105.0
    assert normalized_tick_epoch(
        payload_epoch=100.0,
        receipt_epoch=101.0,
        previous_epoch=103.0,
        market_open_now=False,
        use_receipt_time_for_options=False,
        is_underlying_token=True,
    ) == 103.0
    assert normalized_tick_epoch(payload_epoch=100.0, receipt_epoch=None, previous_epoch=99.0) == 99.0
    assert normalized_tick_epoch(payload_epoch=100.0, receipt_epoch=None, previous_epoch=None) == 0.0
