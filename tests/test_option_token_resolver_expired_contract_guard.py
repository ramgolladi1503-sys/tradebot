from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from core import option_token_resolver as resolver


class _FrozenNow:
    @staticmethod
    def date():
        return date(2026, 5, 22)


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


@pytest.fixture(autouse=True)
def _stable_resolver(monkeypatch):
    monkeypatch.setattr(resolver, "_trading_date", lambda: date(2026, 5, 22))
    monkeypatch.setattr(resolver, "_min_option_token_count", lambda: 1)
    resolver._STATS_LOG_TS.clear()


def test_expired_requested_expiry_rejected_before_cache_lookup(monkeypatch):
    calls = {"load": 0}

    def load(_exchange: str):
        calls["load"] += 1
        return [_inst(token=101, expiry="2026-05-19")], "local_cache"

    monkeypatch.setattr(resolver, "_load_instruments", load)

    result = resolver.resolve_option_token("NIFTY", "2026-05-19", 26000, "CE")

    assert result is None
    assert calls["load"] == 0


def test_expired_local_exact_match_cannot_be_execution_grade(monkeypatch):
    monkeypatch.setattr(
        resolver,
        "_load_instruments",
        lambda _exchange: ([_inst(token=101, expiry="2026-05-19")], "local_cache"),
    )

    result = resolver.resolve_option_token("NIFTY", date(2026, 5, 19), 26000, "CE")

    assert result is None


def test_valid_local_exact_match_remains_execution_grade(monkeypatch):
    monkeypatch.setattr(
        resolver,
        "_load_instruments",
        lambda _exchange: ([_inst(token=202, expiry="2026-05-26")], "local_cache"),
    )

    result = resolver.resolve_option_token("NIFTY", "2026-05-26", 26000, "CE")

    assert result and result["instrument_token"] == 202
    assert result["resolution_path"] == "exact_contract_match"
    assert result["execution_grade"] is True
    assert result["advisory_only"] is False
    assert result["resolved_expiry"] == date(2026, 5, 26)


def test_safe_fallback_skips_expired_contract_and_uses_future_contract(monkeypatch):
    monkeypatch.setattr(
        resolver,
        "_load_instruments",
        lambda _exchange: (
            [
                _inst(token=301, expiry="2026-05-21", strike=26000),
                _inst(token=302, expiry="2026-05-23", strike=26000),
            ],
            "kite_client_cache",
        ),
    )
    monkeypatch.setattr(resolver, "_min_option_token_count", lambda: 1)

    result = resolver.resolve_option_token("NIFTY", "2026-05-22", 26000, "CE")

    assert result and result["instrument_token"] == 302
    assert result["resolution_path"] == "safe_nearest_contract_fallback"
    assert result["execution_grade"] is False
    assert result["advisory_only"] is True
    assert result["resolved_expiry"] == date(2026, 5, 23)


def test_safe_fallback_returns_none_when_only_expired_contract_exists(monkeypatch):
    monkeypatch.setattr(
        resolver,
        "_load_instruments",
        lambda _exchange: ([_inst(token=401, expiry="2026-05-21", strike=26000)], "kite_client_cache"),
    )
    monkeypatch.setattr(resolver, "_min_option_token_count", lambda: 1)

    result = resolver.resolve_option_token("NIFTY", "2026-05-22", 26000, "CE")

    assert result is None


def test_expired_rejection_event_contains_non_action_evidence(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(resolver._LOGGER, "write", events.append)

    result = resolver.resolve_option_token("NIFTY", "2026-05-19", 26000, "CE")

    assert result is None
    assert events
    event = events[-1]
    assert event["event"] == "OPTION_TOKEN_EXPIRED_CONTRACT_REJECTED"
    assert event["code"] == "EXPIRED_CONTRACT_SELECTED"
    assert event["reason"] == "expired_contract_selected"
    assert event["execution_grade"] is False
    assert event["advisory_only"] is True
    assert event["trading_date"] == "2026-05-22"
