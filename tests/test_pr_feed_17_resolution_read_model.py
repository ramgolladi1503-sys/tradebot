from datetime import date

from core.feed.token_resolution_read_model import (
    SymbolResolutionInput,
    build_symbol_resolution_read_model,
    combine_symbol_resolution_models,
    expiry_key,
    infer_atm_strike,
    normalize_and_rank_option_tokens,
    normalize_exchange,
    normalize_positive_tokens,
    normalize_symbol,
    option_distance_rank,
    option_fail_reason,
    selected_option_strikes,
)


OPTION_META = {
    201: {"strike": 19950, "instrument_type": "CE"},
    202: {"strike": 20000, "instrument_type": "CE"},
    203: {"strike": 20000, "instrument_type": "PE"},
    204: {"strike": 20050, "instrument_type": "PE"},
    205: {"strike": 20100, "instrument_type": "CE"},
}


def test_basic_normalizers_are_deterministic():
    assert normalize_symbol(" nifty ") == "NIFTY"
    assert normalize_exchange("", symbol="SENSEX") == "BFO"
    assert normalize_exchange(None, symbol="NIFTY") == "NFO"
    assert normalize_exchange("nfo") == "NFO"
    assert normalize_positive_tokens(["3", 2, 3, 0, -1, None, "bad"]) == (3, 2)
    assert expiry_key(date(2026, 5, 28)) == "2026-05-28"
    assert expiry_key("2026-05-28T00:00:00") == "2026-05-28"
    assert expiry_key("bad") is None
    assert infer_atm_strike(20021.0, 50.0) == 20000
    assert infer_atm_strike(None, 50.0) is None
    assert infer_atm_strike(20021.0, 0.0) is None


def test_option_rank_and_selection_prefers_near_atm_and_tracks_two_sided_strikes():
    assert option_distance_rank(OPTION_META[202], atm=20000, step=50, token=202) == (0.0, 0, 0.0, 0, 202)
    assert option_distance_rank(OPTION_META[203], atm=20000, step=50, token=203) == (0.0, 0, 0.0, 1, 203)
    assert option_distance_rank(OPTION_META[205], atm=20000, step=50, token=205) == (2.0, 1, 100.0, 0, 205)

    tokens, ranks = normalize_and_rank_option_tokens(
        [205, 204, 203, 202, 201, 202],
        option_meta_by_token=OPTION_META,
        atm=20000,
        step=50,
    )
    assert tokens == (202, 203, 201, 204, 205)
    assert ranks[202] == (0.0, 0, 0.0, 0, 202)
    strikes, strike_count, two_sided = selected_option_strikes(tokens, option_meta_by_token=OPTION_META)
    assert strikes == (19950.0, 20000.0, 20050.0, 20100.0)
    assert strike_count == 4
    assert two_sided == 1


def test_fail_reason_is_explicit_and_fail_closed_for_under_min():
    assert option_fail_reason(expiry=None, atm=20000, option_count=10, min_required=4) == "expiry_unavailable"
    assert option_fail_reason(expiry="2026-05-28", atm=None, option_count=10, min_required=4) == "atm_unavailable"
    assert option_fail_reason(expiry="2026-05-28", atm=20000, option_count=1, min_required=4) == "option_tokens_under_min"
    assert option_fail_reason(expiry="2026-05-28", atm=20000, option_count=4, min_required=4) is None


def test_build_symbol_resolution_read_model_for_valid_symbol():
    model = build_symbol_resolution_read_model(
        SymbolResolutionInput(
            symbol="nifty",
            exchange="nfo",
            expiry="2026-05-28",
            ltp=20021.0,
            ltp_source="live_ltp",
            atm=20000,
            strikes_around=2,
            step=50.0,
            index_token="100",
            index_token_source="instruments",
            option_tokens_raw=[205, 204, 203, 202, 201, 202],
            option_meta_by_token=OPTION_META,
            min_option_tokens=4,
        )
    )
    assert model.tokens == (100, 202, 203, 201, 204, 205)
    assert model.underlying_tokens == (100,)
    assert model.underlying_token_to_symbol == {100: "NIFTY"}
    assert model.token_to_symbol[100] == "NIFTY"
    assert model.token_exchange_hint[100] == "NSE"
    assert model.token_exchange_hint[202] == "NFO"
    assert model.row["symbol"] == "NIFTY"
    assert model.row["exchange"] == "NFO"
    assert model.row["expiry"] == "2026-05-28"
    assert model.row["count"] == 6
    assert model.row["option_count"] == 5
    assert model.row["resolved_option_count"] == 5
    assert model.row["option_fail_reason"] is None
    assert model.row["option_two_sided_strike_count"] == 1


def test_build_symbol_resolution_read_model_under_min_drops_options_but_keeps_index():
    model = build_symbol_resolution_read_model(
        SymbolResolutionInput(
            symbol="sensex",
            exchange="",
            expiry="2026-05-28",
            ltp=74000.0,
            ltp_source="fallback_close",
            atm=74000,
            strikes_around=1,
            step=100.0,
            index_token="500",
            index_token_source="config",
            option_tokens_raw=[901],
            option_meta_by_token={901: {"strike": 74000, "instrument_type": "CE"}},
            min_option_tokens=2,
        )
    )
    assert model.tokens == (500,)
    assert model.row["exchange"] == "BFO"
    assert model.row["option_count"] == 0
    assert model.row["resolved_option_count"] == 1
    assert model.row["option_fail_reason"] == "option_tokens_under_min"
    assert model.token_exchange_hint == {500: "BSE"}


def test_combine_symbol_resolution_models_builds_global_read_model_maps():
    nifty = build_symbol_resolution_read_model(
        SymbolResolutionInput(
            symbol="NIFTY",
            exchange="NFO",
            expiry="2026-05-28",
            ltp=20000.0,
            ltp_source="live_ltp",
            atm=20000,
            strikes_around=1,
            step=50.0,
            index_token=100,
            index_token_source="instruments",
            option_tokens_raw=[202, 203],
            option_meta_by_token=OPTION_META,
            min_option_tokens=2,
        )
    )
    sensex = build_symbol_resolution_read_model(
        SymbolResolutionInput(
            symbol="SENSEX",
            exchange="BFO",
            expiry="2026-05-29",
            ltp=74000.0,
            ltp_source="live_ltp",
            atm=74000,
            strikes_around=1,
            step=100.0,
            index_token=500,
            index_token_source="instruments",
            option_tokens_raw=[902, 903],
            option_meta_by_token={
                902: {"strike": 74000, "instrument_type": "CE"},
                903: {"strike": 74000, "instrument_type": "PE"},
            },
            min_option_tokens=2,
        )
    )
    combined = combine_symbol_resolution_models([nifty, sensex])
    assert combined.tokens == (100, 202, 203, 500, 902, 903)
    assert combined.underlying_tokens == frozenset({100, 500})
    assert combined.underlying_token_to_symbol == {100: "NIFTY", 500: "SENSEX"}
    assert combined.option_counts_by_symbol == {"NIFTY": 2, "SENSEX": 2}
    assert combined.option_min_required_by_symbol == {"NIFTY": 2, "SENSEX": 2}
    payload = combined.to_payload()
    assert payload["tokens"] == [100, 202, 203, 500, 902, 903]
    assert len(payload["resolution"]) == 2
