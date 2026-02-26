from dashboard.upstox_links import build_upstox_search_query


def test_build_search_query_format():
    row = {
        "underlying": "BANKNIFTY",
        "expiry_date": "2026-02-27",
        "strike": 61200,
        "option_type": "CE",
    }
    query = build_upstox_search_query(row)
    assert query == "BANKNIFTY 27 FEB 61200 CE"
