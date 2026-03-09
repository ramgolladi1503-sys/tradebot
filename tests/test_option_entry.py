from core.option_entry import validate_live_entry
from core.review_queue import _normalize_queue_row


def test_entry_requires_live_option_ltp():
    out = validate_live_entry(signal_price=100.0, current_ltp=None, ltp_ts_epoch=None, now_epoch=100.0)
    assert out["valid"] is False
    assert out["entry_status"] == "NO_LIVE_OPTION_FEED"


def test_entry_invalidated_when_price_mismatch():
    out = validate_live_entry(
        signal_price=100.0,
        current_ltp=140.0,
        ltp_ts_epoch=100.0,
        now_epoch=101.0,
        mismatch_pct=0.03,
        max_age_sec=2.0,
    )
    assert out["valid"] is True
    assert out["entry_status"] == "PRICE_MISMATCH"
    assert out["suggested_entry"] == 140.0


def test_entry_strict_mismatch_is_non_blocking():
    out = validate_live_entry(
        signal_price=100.0,
        current_ltp=140.0,
        ltp_ts_epoch=100.0,
        now_epoch=101.0,
        mismatch_pct=0.03,
        max_age_sec=2.0,
        require_strict_match=True,
    )
    assert out["valid"] is True
    assert out["entry_status"] == "PRICE_MISMATCH"


def test_option_entry_matches_ltp_within_tolerance():
    out = validate_live_entry(
        signal_price=100.0,
        current_ltp=101.0,
        ltp_ts_epoch=100.0,
        now_epoch=101.0,
        mismatch_pct=0.03,
        max_age_sec=2.0,
    )
    assert out["valid"] is True
    assert out["suggested_entry"] == 101.0


def test_option_entry_emits_freshness_evidence():
    out = validate_live_entry(
        symbol="NIFTY",
        trade_id="A-1",
        signal_price=100.0,
        current_ltp=101.0,
        ltp_ts_epoch=100.0,
        now_epoch=102.1,
        mismatch_pct=0.03,
        max_age_sec=8.0,
        market_open=True,
    )

    assert out["freshness_reason"] == "quote_within_threshold"
    assert out["freshness_selected_source"] == "quote"
    assert abs(float(out["freshness_selected_age_sec"]) - 2.1) < 1e-6
    assert abs(float(out["price_age_sec"]) - 2.1) < 1e-6
    assert out["freshness_decision"]["trade_id"] == "A-1"


def test_option_entry_uses_candle_fallback_when_quote_timestamp_missing():
    out = validate_live_entry(
        symbol="NIFTY",
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=None,
        candle_ts_epoch=100.0,
        now_epoch=106.0,
        max_age_sec=8.0,
        allow_candle_fallback=True,
        market_open=True,
    )

    assert out["valid"] is True
    assert out["entry_status"] == "OK"
    assert out["freshness_reason"] == "fallback_to_candle_within_threshold"
    assert out["freshness_selected_source"] == "candle"


def test_queue_row_with_missing_entry_is_marked_invalid_for_planning():
    row = _normalize_queue_row(
        {
            "symbol": "NIFTY",
            "status": "PLANNING",
            "entry": None,
            "entry_status": "NO_LIVE_OPTION_FEED",
            "timestamp": "2026-03-04T09:20:00Z",
        }
    )
    assert row["status"] == "INVALID"
    assert row["permission"] == "ADVISORY_ONLY"
    assert row["entry_status"] in {"NO_LIVE_OPTION_FEED", "MISSING_ENTRY"}
    assert row["entry"] is None


def test_queue_row_with_numeric_entry_remains_eligible_status():
    row = _normalize_queue_row(
        {
            "symbol": "NIFTY",
            "status": "ACTIVE",
            "entry": 101.25,
            "entry_status": "OK",
            "timestamp": "2026-03-04T09:20:00Z",
        }
    )
    assert row["status"] == "ACTIVE"
    assert float(row["entry"]) == 101.25
