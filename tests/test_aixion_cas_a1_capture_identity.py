from __future__ import annotations

import pytest

from aixion_trade_intelligence.cas_a1_capture_identity import (
    FROZEN_DEVELOPMENT_SYMBOLS,
    CasA1CaptureIdentityError,
    build_capture_identity_contract,
)


def _live_universe():
    current = [symbol for symbol in FROZEN_DEVELOPMENT_SYMBOLS if symbol not in {"HEROMOTOCO", "INDUSINDBK"}]
    current += ["INDIGO", "MAXHEALTH", "TMPV"]
    return {
        "canonical_sha256": "abc123",
        "provider_native_index_identifier": "NIFTY 50",
        "index_instrument_token": 256265,
        "constituents": [
            {"symbol": symbol, "instrument_token": 10000 + i}
            for i, symbol in enumerate(current)
        ],
    }


def _instrument_master():
    return [
        {
            "tradingsymbol": "HEROMOTOCO",
            "exchange": "NSE",
            "segment": "NSE",
            "instrument_type": "EQ",
            "instrument_token": 345089,
        },
        {
            "tradingsymbol": "INDUSINDBK",
            "exchange": "NSE",
            "segment": "NSE",
            "instrument_type": "EQ",
            "instrument_token": 1346049,
        },
    ]


def test_planner_preserves_exact_frozen_49_and_exposes_supplemental_capture():
    contract = build_capture_identity_contract(
        live_universe=_live_universe(),
        broker_instrument_master=_instrument_master(),
    )
    assert len(contract["constituents"]) == 49
    assert [row["symbol"] for row in contract["constituents"]] == list(FROZEN_DEVELOPMENT_SYMBOLS)
    assert contract["requires_supplemental_capture"] is True
    assert [row["symbol"] for row in contract["supplemental_constituents"]] == ["HEROMOTOCO", "INDUSINDBK"]
    assert contract["ignored_current_symbols"] == ["INDIGO", "MAXHEALTH", "TMPV"]
    assert contract["broker_write_authority"] is False
    assert contract["order_authority"] is False
    assert contract["live_authorized"] is False


def test_missing_supplemental_symbol_in_master_fails_closed():
    master = _instrument_master()[:-1]
    with pytest.raises(CasA1CaptureIdentityError, match="INDUSINDBK"):
        build_capture_identity_contract(
            live_universe=_live_universe(),
            broker_instrument_master=master,
        )


def test_ambiguous_supplemental_token_fails_closed():
    master = _instrument_master()
    master.append({
        "tradingsymbol": "HEROMOTOCO",
        "exchange": "NSE",
        "segment": "NSE",
        "instrument_type": "EQ",
        "instrument_token": 999999,
    })
    with pytest.raises(CasA1CaptureIdentityError, match="HEROMOTOCO"):
        build_capture_identity_contract(
            live_universe=_live_universe(),
            broker_instrument_master=master,
        )
