from __future__ import annotations

from datetime import date, datetime

from core.instruments import build_option_registry, resolve_registry_contract


def _inst(
    *,
    name: str,
    segment: str,
    strike: float,
    instrument_type: str,
    expiry,
    instrument_token: int,
    tradingsymbol: str,
):
    return {
        "name": name,
        "segment": segment,
        "strike": strike,
        "instrument_type": instrument_type,
        "expiry": expiry,
        "instrument_token": instrument_token,
        "tradingsymbol": tradingsymbol,
    }


def test_build_option_registry_loads_expiry_types():
    payload = build_option_registry(
        symbol="BANKNIFTY",
        exchange="NFO",
        instruments=[
            _inst(
                name="BANKNIFTY",
                segment="NFO-OPT",
                strike=48000,
                instrument_type="CE",
                expiry=date(2030, 1, 28),
                instrument_token=101,
                tradingsymbol="BANKNIFTY30JAN48000CE",
            ),
            _inst(
                name="BANKNIFTY",
                segment="NFO-OPT",
                strike=48000,
                instrument_type="PE",
                expiry="2030-02-04T00:00:00",
                instrument_token=102,
                tradingsymbol="BANKNIFTY04FEB48000PE",
            ),
            _inst(
                name="BANKNIFTY",
                segment="NFO-OPT",
                strike=48000,
                instrument_type="CE",
                expiry=datetime(2030, 2, 4, 9, 15),
                instrument_token=103,
                tradingsymbol="BANKNIFTY04FEB48000CE",
            ),
        ],
    )

    assert payload["available_expiries"] == [date(2030, 1, 28), date(2030, 2, 4)]
    key = ("BANKNIFTY", "NFO-OPT", 48000.0, "CE", date(2030, 1, 28))
    assert key in payload["registry"]
    assert payload["registry"][key]["instrument_token"] == 101
    assert payload["registry"][key]["tradingsymbol"] == "BANKNIFTY30JAN48000CE"
    assert payload["registry"][key]["expiry"] == date(2030, 1, 28)


def test_contract_selection_picks_valid_instrument_token():
    payload = build_option_registry(
        symbol="BANKNIFTY",
        exchange="NFO",
        instruments=[
            _inst(
                name="BANKNIFTY",
                segment="NFO-OPT",
                strike=48000,
                instrument_type="CE",
                expiry=date(2030, 1, 28),
                instrument_token=201,
                tradingsymbol="BANKNIFTY28JAN48000CE",
            ),
            _inst(
                name="BANKNIFTY",
                segment="NFO-OPT",
                strike=48000,
                instrument_type="CE",
                expiry=date(2030, 1, 30),
                instrument_token=202,
                tradingsymbol="BANKNIFTY30JAN48000CE",
            ),
            _inst(
                name="BANKNIFTY",
                segment="NFO-OPT",
                strike=48000,
                instrument_type="CE",
                expiry=date(2030, 2, 6),
                instrument_token=203,
                tradingsymbol="BANKNIFTY06FEB48000CE",
            ),
        ],
    )

    nearest = resolve_registry_contract(
        registry_payload=payload,
        symbol="BANKNIFTY",
        strike=48000,
        instrument_type="CE",
        selection_mode="NEAREST",
        today=date(2030, 1, 27),
    )
    assert nearest is not None
    assert nearest["instrument_token"] == 201

    monthly = resolve_registry_contract(
        registry_payload=payload,
        symbol="BANKNIFTY",
        strike=48000,
        instrument_type="CE",
        selection_mode="MONTHLY",
        today=date(2030, 1, 27),
    )
    assert monthly is not None
    assert monthly["instrument_token"] == 202
