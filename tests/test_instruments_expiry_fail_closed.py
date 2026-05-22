from __future__ import annotations

from datetime import date

from core.instruments import build_option_registry, resolve_registry_contract, select_expiry


def _inst(*, token: int, expiry: str, strike: float = 26000.0, opt_type: str = "CE", name: str = "NIFTY") -> dict:
    return {
        "instrument_token": token,
        "tradingsymbol": f"{name}{expiry.replace('-', '')}{int(strike)}{opt_type}",
        "name": name,
        "segment": "NFO-OPT",
        "instrument_type": opt_type,
        "expiry": expiry,
        "strike": strike,
    }


def test_select_expiry_returns_none_when_all_expiries_are_expired():
    result = select_expiry(
        ["2026-05-12", "2026-05-19"],
        today=date(2026, 5, 22),
    )

    assert result is None


def test_select_expiry_allows_same_day_expiry():
    result = select_expiry(
        ["2026-05-22", "2026-05-26"],
        today=date(2026, 5, 22),
    )

    assert result == date(2026, 5, 22)


def test_resolve_registry_contract_rejects_expired_requested_expiry():
    registry = build_option_registry(
        symbol="NIFTY",
        instruments=[_inst(token=101, expiry="2026-05-19")],
        exchange="NFO",
    )

    result = resolve_registry_contract(
        registry_payload=registry,
        symbol="NIFTY",
        strike=26000,
        instrument_type="CE",
        requested_expiry="2026-05-19",
        today=date(2026, 5, 22),
    )

    assert result is None


def test_resolve_registry_contract_does_not_fallback_to_expired_when_only_old_expiries_exist():
    registry = build_option_registry(
        symbol="NIFTY",
        instruments=[_inst(token=101, expiry="2026-05-19")],
        exchange="NFO",
    )

    result = resolve_registry_contract(
        registry_payload=registry,
        symbol="NIFTY",
        strike=26000,
        instrument_type="CE",
        today=date(2026, 5, 22),
    )

    assert result is None


def test_resolve_registry_contract_selects_future_expiry_when_no_request_given():
    registry = build_option_registry(
        symbol="NIFTY",
        instruments=[
            _inst(token=101, expiry="2026-05-19"),
            _inst(token=202, expiry="2026-05-26"),
        ],
        exchange="NFO",
    )

    result = resolve_registry_contract(
        registry_payload=registry,
        symbol="NIFTY",
        strike=26000,
        instrument_type="CE",
        today=date(2026, 5, 22),
    )

    assert result is not None
    assert result["instrument_token"] == 202
    assert result["expiry"] == date(2026, 5, 26)
