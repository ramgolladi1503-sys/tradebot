from core.trailing_display import apply_trailing_display_row


def test_trailing_columns_hidden_in_planning():
    row = {
        "status": "PLANNING",
        "trail_enabled": True,
        "trail_rule": "MFE_MINUS_OFFSET",
        "trail_offset": 5.0,
        "trail_start": "AFTER_1R",
        "mfe_price": 120.0,
        "trail_stop": 110.0,
        "stop": 105.0,
        "entry": 100.0,
        "side": "BUY",
    }
    out = apply_trailing_display_row(row)
    assert out["trail_rule"] == "MFE_MINUS_OFFSET"
    assert out["trail_start"] == "AFTER_1R"
    assert out["mfe_price"] is None
    assert out["trail_stop"] is None
    assert out["current_stop"] is None


def test_trailing_columns_present_in_active():
    row = {
        "status": "ACTIVE",
        "trail_enabled": True,
        "trail_rule": "MFE_MINUS_OFFSET",
        "trail_offset": 5.0,
        "trail_start": "AFTER_1R",
        "mfe_price": 120.0,
        "trail_stop": 112.0,
        "stop": 112.0,
        "entry": 100.0,
        "side": "BUY",
    }
    out = apply_trailing_display_row(row)
    assert out["mfe_price"] == 120.0
    assert out["trail_stop"] == 112.0
    assert out["current_stop"] == 112.0
    assert out["profit_locked"] is True
