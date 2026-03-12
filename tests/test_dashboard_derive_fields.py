from dashboard.ui.utils.derive_fields import (
    map_strategy_category,
    parse_option_side,
    parse_underlying,
)


def test_parse_option_side():
    assert parse_option_side("NIFTY26MAR22500CE") == "CE"
    assert parse_option_side("BANKNIFTY 51000 PE") == "PE"
    assert parse_option_side("SENSEX-CALL") == "CE"
    assert parse_option_side("NIFTY|2026-03-17|23850|PE") == "PE"
    assert parse_option_side("NIFTYSPOT") == "UNKNOWN"


def test_parse_underlying():
    assert parse_underlying("NIFTY26MAR22500CE") == "NIFTY"
    assert parse_underlying("BANKNIFTY 51000 PE") == "BANKNIFTY"
    assert parse_underlying("BSE:SENSEX") == "SENSEX"
    assert parse_underlying("FINNIFTY") == "NIFTY"


def test_map_strategy_category():
    assert map_strategy_category("trend_vwap") == "TREND"
    assert map_strategy_category("mean_reversion_core") == "MEAN_REVERT"
    assert map_strategy_category("event_breakout") == "EVENT"
    assert map_strategy_category("mystery_strategy") == "UNKNOWN"
