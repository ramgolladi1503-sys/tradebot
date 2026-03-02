from core.option_entry import validate_live_entry


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
    assert out["valid"] is False
    assert out["entry_status"] == "STALE_PRICE"


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

