from dashboard.upstox_links import build_upstox_contract_url, build_upstox_search_query


def test_unresolved_contract_disables_open():
    row = {"symbol": "BANKNIFTY"}
    query = build_upstox_search_query(row)
    assert query == "BANKNIFTY"
    assert build_upstox_contract_url("") == ""
