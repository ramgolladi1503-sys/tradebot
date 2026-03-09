from core.option_entry import validate_live_entry


def test_live_strict_blocks_stale_option_ltp():
    out = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=106.0,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        segment="NSE_FNO",
        token=12345,
        require_token=True,
    )
    assert out["valid"] is False
    assert out["entry_status"] == "STALE_OPTION_LTP"


def test_planning_or_allow_stale_does_not_block_stale_option_ltp():
    out = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=500.0,
        mode="PAPER",
        allow_stale_quotes=True,
        token=12345,
        require_token=True,
    )
    assert out["valid"] is True
    assert out["entry_status"] == "OK"


def test_missing_token_returns_missing_option_token_reason():
    out = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=101.0,
        mode="LIVE",
        allow_stale_quotes=False,
        token=None,
        require_token=True,
    )
    assert out["valid"] is False
    assert out["entry_status"] == "MISSING_OPTION_TOKEN"


def test_live_mode_market_closed_uses_planning_sla():
    out = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=220.0,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=False,
        segment="NSE_FNO",
        token=12345,
        require_token=True,
    )
    assert out["valid"] is True
    assert out["entry_status"] == "OK"
