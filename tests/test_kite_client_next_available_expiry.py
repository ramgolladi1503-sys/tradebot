from __future__ import annotations

import json
from datetime import date

from core.kite_client import KiteClient


def _option_row(
    *,
    name: str,
    tradingsymbol: str,
    expiry: date,
    exchange: str,
    instrument_type: str = "OPTIDX",
    segment: str | None = None,
    strike: float = 0.0,
    instrument_token: int | None = None,
) -> dict:
    return {
        "name": name,
        "tradingsymbol": tradingsymbol,
        "expiry": expiry,
        "segment": segment if segment is not None else f"{exchange}-OPT",
        "exchange": exchange,
        "instrument_type": instrument_type,
        "strike": strike,
        "instrument_token": instrument_token,
    }


def test_next_available_expiry_matches_nifty_from_tradingsymbol_when_name_blank(monkeypatch):
    client = KiteClient()
    logs: list[str] = []
    rows = [
        _option_row(name="", tradingsymbol="NIFTY26MAR25000CE", expiry=date(2026, 3, 26), exchange="NFO"),
        _option_row(name="", tradingsymbol="NIFTY02APR25000CE", expiry=date(2026, 4, 2), exchange="NFO"),
    ]
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: logs.append(str(msg)))

    resolved = client.next_available_expiry("NIFTY", exchange="NFO")

    assert resolved == date(2026, 3, 26)
    payload = json.loads(logs[-1])
    assert payload["exchange"] == "NFO"
    assert payload["symbol"] == "NIFTY"
    assert payload["total_option_candidates_scanned"] == 2
    assert payload["matched_candidates_count"] == 2
    assert payload["sample_segments"] == ["NFO-OPT"]
    assert payload["sample_instrument_types"] == ["OPTIDX"]
    assert payload["candidate_tradingsymbols"][0] == "NIFTY26MAR25000CE"
    assert payload["matched_tradingsymbols"][0] == "NIFTY26MAR25000CE"
    assert payload["resolved_expiry"] == "2026-03-26"


def test_next_available_expiry_does_not_match_banknifty_to_nifty(monkeypatch):
    client = KiteClient()
    rows = [
        _option_row(name="", tradingsymbol="NIFTY26MAR25000CE", expiry=date(2026, 3, 26), exchange="NFO"),
        _option_row(name="", tradingsymbol="BANKNIFTY26MAR48000CE", expiry=date(2026, 3, 26), exchange="NFO"),
    ]
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.next_available_expiry("BANKNIFTY", exchange="NFO")

    assert resolved == date(2026, 3, 26)


def test_next_available_expiry_accepts_ce_pe_instrument_types(monkeypatch):
    client = KiteClient()
    rows = [
        _option_row(
            name="",
            tradingsymbol="NIFTY26MAR25000CE",
            expiry=date(2026, 3, 26),
            exchange="NFO",
            instrument_type="CE",
            segment="NFO-FNO",
        ),
        _option_row(
            name="",
            tradingsymbol="NIFTY26APR25000PE",
            expiry=date(2026, 4, 30),
            exchange="NFO",
            instrument_type="PE",
            segment="NFO-FNO",
        ),
    ]
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.next_available_expiry("NIFTY", exchange="NFO")

    assert resolved == date(2026, 3, 26)


def test_next_available_expiry_matches_sensex_on_bfo(monkeypatch):
    client = KiteClient()
    rows = [
        _option_row(name="", tradingsymbol="SENSEX26MAR80000CE", expiry=date(2026, 3, 26), exchange="BFO"),
    ]
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.next_available_expiry("SENSEX", exchange="BFO")

    assert resolved == date(2026, 3, 26)


def test_next_available_expiry_accepts_tradingsymbol_suffix_without_option_segment(monkeypatch):
    client = KiteClient()
    rows = [
        _option_row(
            name="",
            tradingsymbol="NIFTY26MAR25000PE",
            expiry=date(2026, 3, 26),
            exchange="NFO",
            instrument_type="FUT",
            segment="NFO-FUT",
        ),
    ]
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.next_available_expiry("NIFTY", exchange="NFO")

    assert resolved == date(2026, 3, 26)


def test_next_available_expiry_returns_none_when_no_rows_match(monkeypatch):
    client = KiteClient()
    logs: list[str] = []
    rows = [
        _option_row(name="", tradingsymbol="BANKNIFTY26MAR48000CE", expiry=date(2026, 3, 26), exchange="NFO"),
    ]
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: logs.append(str(msg)))

    resolved = client.next_available_expiry("NIFTY", exchange="NFO")

    assert resolved is None
    payload = json.loads(logs[-1])
    assert payload["matched_candidates_count"] == 0
    assert payload["resolved_expiry"] == "none"


def _window_rows(
    symbol: str,
    exchange: str,
    expiry: date,
    atm: int,
    step: int,
    instrument_type: str,
    start_token: int = 100000,
) -> list[dict]:
    rows: list[dict] = []
    next_token = int(start_token)
    for off in range(-6, 7):
        strike = atm + (off * step)
        for opt_type in ("CE", "PE"):
            rows.append(
                _option_row(
                    name="",
                    tradingsymbol=f"{symbol}{expiry.strftime('%d%b').upper()}{strike}{opt_type}",
                    expiry=expiry,
                    exchange=exchange,
                    instrument_type=instrument_type if instrument_type in {"CE", "PE"} else opt_type,
                    segment=f"{exchange}-OPT",
                    strike=float(strike),
                    instrument_token=next_token,
                )
            )
            next_token += 1
    return rows


def test_resolve_option_tokens_window_defaults_accept_nfo_ce_pe_rows(monkeypatch):
    client = KiteClient()
    expiry = date(2026, 3, 26)
    rows = _window_rows("NIFTY", "NFO", expiry, atm=22000, step=50, instrument_type="CE", start_token=100000)
    rows.extend(
        _window_rows("BANKNIFTY", "NFO", expiry, atm=48000, step=100, instrument_type="PE", start_token=200000)
    )
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.resolve_option_tokens_window(
        symbol="NIFTY",
        expiry=expiry,
        strikes_around=6,
        exchange="NFO",
        spot=None,
    )

    assert len(resolved) == 26
    assert all(isinstance(token, int) for token in resolved)


def test_resolve_option_tokens_window_defaults_accept_bfo_ce_pe_rows(monkeypatch):
    client = KiteClient()
    expiry = date(2026, 3, 26)
    rows = _window_rows("SENSEX", "BFO", expiry, atm=83000, step=100, instrument_type="PE")
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.resolve_option_tokens_window(
        symbol="SENSEX",
        expiry=expiry,
        strikes_around=6,
        exchange="BFO",
        spot=None,
    )

    assert len(resolved) == 26


def test_resolve_option_tokens_window_uses_tradingsymbol_suffix_detection(monkeypatch):
    client = KiteClient()
    expiry = date(2026, 3, 26)
    rows = []
    next_token = 200000
    for off in range(-6, 7):
        strike = 22000 + (off * 50)
        for opt_type in ("CE", "PE"):
            rows.append(
                _option_row(
                    name="",
                    tradingsymbol=f"NIFTY{expiry.strftime('%d%b').upper()}{strike}{opt_type}",
                    expiry=expiry,
                    exchange="NFO",
                    instrument_type="FUT",
                    segment="NFO-FUT",
                    strike=float(strike),
                    instrument_token=next_token,
                )
            )
            next_token += 1
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.resolve_option_tokens_window(
        symbol="NIFTY",
        expiry=expiry,
        strikes_around=6,
        exchange="NFO",
        spot=None,
    )

    assert len(resolved) == 26


def test_resolve_option_tokens_window_does_not_false_match_banknifty_to_nifty(monkeypatch):
    client = KiteClient()
    expiry = date(2026, 3, 26)
    rows = _window_rows("NIFTY", "NFO", expiry, atm=22000, step=50, instrument_type="CE", start_token=100000)
    rows.extend(
        _window_rows("BANKNIFTY", "NFO", expiry, atm=48000, step=100, instrument_type="PE", start_token=200000)
    )
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.resolve_option_tokens_window(
        symbol="BANKNIFTY",
        expiry=expiry,
        strikes_around=6,
        exchange="NFO",
        spot=None,
    )

    assert len(resolved) == 26
    assert set(resolved).isdisjoint(
        {
            int(row["instrument_token"])
            for row in rows
            if str(row.get("tradingsymbol") or "").upper().startswith("NIFTY")
        }
    )


def test_resolve_option_tokens_window_logs_zero_token_diagnostics(monkeypatch):
    client = KiteClient()
    logs: list[str] = []
    expiry = date(2026, 3, 26)
    rows = _window_rows("NIFTY", "NFO", expiry, atm=22000, step=50, instrument_type="CE")
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: logs.append(str(msg)))

    resolved = client.resolve_option_tokens_window(
        symbol="NIFTY",
        expiry=expiry,
        strikes_around=6,
        exchange="NFO",
        include_ce=False,
        include_pe=False,
        spot=None,
    )

    assert resolved == []
    payload = json.loads(logs[-1])
    assert payload["event"] == "KITE_OPTION_WINDOW_RESOLUTION"
    assert payload["symbol"] == "NIFTY"
    assert payload["total_rows_scanned"] == 26
    assert payload["option_rows_matched"] == 26
    assert payload["expiry_matched_rows"] == 26
    assert payload["strike_window_matched_rows"] == 26
    assert payload["final_token_count"] == 0
    assert payload["failure_reason"] == "no_tokens_after_leg_filter"


def test_is_option_instrument_row_rejects_non_option_suffix_false_positive():
    client = KiteClient()

    assert client._is_option_instrument_row(
        {
            "segment": "NSE-EQ",
            "instrument_type": "EQ",
            "tradingsymbol": "RELIANCE",
            "strike": 0.0,
            "expiry": None,
        }
    ) is False
    assert client._is_option_instrument_row(
        {
            "segment": "NFO-FUT",
            "instrument_type": "FUT",
            "tradingsymbol": "NIFTY26MARFUT",
            "strike": 22000.0,
            "expiry": date(2026, 3, 26),
        }
    ) is False


def test_resolve_option_tokens_window_none_instrument_types_uses_defaults(monkeypatch):
    client = KiteClient()
    expiry = date(2026, 3, 26)
    rows = _window_rows("NIFTY", "NFO", expiry, atm=22000, step=50, instrument_type="CE")
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: None)

    resolved = client.resolve_option_tokens_window(
        symbol="NIFTY",
        expiry=expiry,
        strikes_around=6,
        exchange="NFO",
        instrument_types=None,
        spot=None,
    )

    assert len(resolved) == 26


def test_resolve_option_tokens_window_empty_instrument_types_is_explicit_zero(monkeypatch):
    client = KiteClient()
    logs: list[str] = []
    expiry = date(2026, 3, 26)
    rows = _window_rows("NIFTY", "NFO", expiry, atm=22000, step=50, instrument_type="CE")
    monkeypatch.setattr(client, "instruments", lambda exchange=None: list(rows))
    monkeypatch.setattr(client, "_log_atomic", lambda msg: logs.append(str(msg)))

    resolved = client.resolve_option_tokens_window(
        symbol="NIFTY",
        expiry=expiry,
        strikes_around=6,
        exchange="NFO",
        instrument_types=(),
        spot=None,
    )

    assert resolved == []
    payload = json.loads(logs[-1])
    assert payload["event"] == "KITE_OPTION_WINDOW_RESOLUTION"
    assert payload["failure_reason"] == "instrument_types_empty"
    assert payload["final_token_count"] == 0
