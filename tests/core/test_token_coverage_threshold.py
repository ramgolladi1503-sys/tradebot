from __future__ import annotations

from datetime import date

import pytest

from config import config as cfg
import core.option_token_resolver as resolver


FUTURE_EXPIRY = "2099-05-26"


def _instrument_row(*, token: int, strike: float, opt_type: str, expiry: str = FUTURE_EXPIRY) -> dict:
    return {
        "segment": "NFO-OPT",
        "name": "NIFTY",
        "expiry": expiry,
        "strike": float(strike),
        "instrument_type": str(opt_type).upper(),
        "instrument_token": int(token),
        "tradingsymbol": f"NIFTY{expiry.replace('-', '')}{int(strike)}{str(opt_type).upper()}",
    }


class _CaptureLogger:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def write(self, payload: dict) -> bool:
        self.rows.append(dict(payload))
        return True


def _make_contracts(count: int) -> list[dict]:
    contracts: list[dict] = []
    strike = 24000.0
    token = 1_000_000
    for idx in range(count):
        contracts.append(
            _instrument_row(
                token=token + idx,
                strike=strike + (idx * 50.0),
                opt_type="CE" if idx % 2 == 0 else "PE",
            )
        )
    return contracts


def test_token_coverage_below_threshold_raises(monkeypatch):
    contracts = _make_contracts(8)
    capture = _CaptureLogger()
    monkeypatch.setattr(resolver, "_LOGGER", capture)
    monkeypatch.setattr(resolver, "_load_instruments", lambda exchange: (contracts, "unit_test"), raising=True)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 20, raising=False)

    with pytest.raises(resolver.TokenCoverageError) as exc_info:
        resolver.resolve_option_token(
            symbol="NIFTY",
            expiry_date=date(2099, 5, 26),
            strike=24000.0,
            option_type="CE",
            exchange="NFO",
        )

    assert exc_info.value.code == "TOKEN_COVERAGE_BELOW_THRESHOLD"
    assert int(exc_info.value.evidence.get("resolved_option_tokens_count") or 0) == 8
    assert int(exc_info.value.evidence.get("min_option_token_count") or 0) == 20
    assert any(row.get("event") == "OPTION_TOKEN_COVERAGE_BELOW_THRESHOLD" for row in capture.rows)


def test_token_coverage_above_threshold_returns_token(monkeypatch):
    contracts = _make_contracts(60)
    capture = _CaptureLogger()
    monkeypatch.setattr(resolver, "_LOGGER", capture)
    monkeypatch.setattr(resolver, "_load_instruments", lambda exchange: (contracts, "unit_test"), raising=True)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 50, raising=False)

    out = resolver.resolve_option_token(
        symbol="NIFTY",
        expiry_date=FUTURE_EXPIRY,
        strike=24000.0,
        option_type="CE",
        exchange="NFO",
    )

    assert isinstance(out, dict)
    assert int(out.get("instrument_token") or 0) > 0
    assert not any(row.get("event") == "OPTION_TOKEN_COVERAGE_BELOW_THRESHOLD" for row in capture.rows)
