from core.option_chain import _derive_option_price_fields


def test_mark_price_prefers_mid_when_last_outside_bidask():
    fields = _derive_option_price_fields(
        last_price=150.0,
        best_bid=100.0,
        best_ask=102.0,
        quote_age_sec=1.0,
        max_quote_age_sec=8.0,
    )
    assert round(fields["mark_price"], 2) == 101.00
    assert fields["price_source"] == "mid"
    assert round(fields["entry_price_proxy_buy"], 2) == 102.00
    assert round(fields["entry_price_proxy_sell"], 2) == 100.00

