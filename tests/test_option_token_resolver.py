from __future__ import annotations

import json
import pytest

from config import config as cfg
import core.option_token_resolver as resolver


class _CaptureLogger:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def write(self, payload: dict) -> bool:
        self.rows.append(dict(payload))
        return True


def _instrument_row(*, token: int, strike: float, opt_type: str) -> dict:
    return {
        "segment": "NFO-OPT",
        "name": "NIFTY",
        "expiry": "2026-03-02",
        "strike": float(strike),
        "instrument_type": str(opt_type).upper(),
        "instrument_token": int(token),
        "tradingsymbol": f"NIFTY26MAR{int(strike)}{str(opt_type).upper()}",
    }


def test_resolver_prefers_local_cache_and_logs_registry_stats(monkeypatch, tmp_path):
    cache_path = tmp_path / "kite_instruments.json"
    cache_path.write_text(
        json.dumps(
            {
                "NFO": [
                    _instrument_row(token=111, strike=24600.0, opt_type="PE"),
                    _instrument_row(token=222, strike=24600.0, opt_type="CE"),
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(resolver, "data_root", lambda: tmp_path)
    monkeypatch.setattr(
        resolver.kite_client,
        "instruments_cached",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should_not_call_kite_client")),
    )
    capture = _CaptureLogger()
    monkeypatch.setattr(resolver, "_LOGGER", capture)
    resolver._STATS_LOG_TS.clear()
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 1, raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 1, raising=False)

    out = resolver.resolve_option_token(
        symbol="NIFTY",
        expiry_date="2026-03-02",
        strike=24600.0,
        option_type="PE",
        exchange="NFO",
    )

    assert out is not None
    assert int(out["instrument_token"]) == 111
    stats_rows = [row for row in capture.rows if row.get("event") == "OPTION_TOKEN_REGISTRY_STATS"]
    assert stats_rows
    assert int(stats_rows[-1]["resolved_tokens_count"]) == 2
    assert "local_cache" in str(stats_rows[-1].get("data_source"))


def test_resolver_logs_under_min_token_count(monkeypatch, tmp_path):
    cache_path = tmp_path / "kite_instruments.json"
    cache_path.write_text(
        json.dumps({"NFO": [_instrument_row(token=333, strike=24650.0, opt_type="CE")]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(resolver, "data_root", lambda: tmp_path)
    monkeypatch.setattr(resolver.kite_client, "instruments_cached", lambda *_args, **_kwargs: [])
    capture = _CaptureLogger()
    monkeypatch.setattr(resolver, "_LOGGER", capture)
    resolver._STATS_LOG_TS.clear()
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 3, raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 3, raising=False)

    with pytest.raises(resolver.TokenCoverageError) as exc_info:
        resolver.resolve_option_token(
            symbol="NIFTY",
            expiry_date="2026-03-02",
            strike=24700.0,
            option_type="CE",
            exchange="NFO",
        )

    assert exc_info.value.code == "TOKEN_COVERAGE_BELOW_THRESHOLD"
    under_min = [row for row in capture.rows if row.get("event") == "OPTION_TOKEN_REGISTRY_UNDER_MIN"]
    assert under_min
    assert int(under_min[-1]["resolved_tokens_count"]) == 1
    assert int(under_min[-1]["min_required"]) == 3
    threshold_rows = [row for row in capture.rows if row.get("event") == "OPTION_TOKEN_COVERAGE_BELOW_THRESHOLD"]
    assert threshold_rows


def test_resolver_returns_exact_contract_match_even_when_coverage_is_below_threshold(monkeypatch, tmp_path):
    cache_path = tmp_path / "kite_instruments.json"
    cache_path.write_text(
        json.dumps({"NFO": [_instrument_row(token=333, strike=24650.0, opt_type="CE")]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(resolver, "data_root", lambda: tmp_path)
    monkeypatch.setattr(resolver.kite_client, "instruments_cached", lambda *_args, **_kwargs: [])
    capture = _CaptureLogger()
    monkeypatch.setattr(resolver, "_LOGGER", capture)
    resolver._STATS_LOG_TS.clear()
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKEN_COUNT", 3, raising=False)
    monkeypatch.setattr(cfg, "MIN_OPTION_TOKENS", 3, raising=False)

    out = resolver.resolve_option_token(
        symbol="NIFTY",
        expiry_date="2026-03-02",
        strike=24650.0,
        option_type="CE",
        exchange="NFO",
    )

    assert out is not None
    assert int(out["instrument_token"]) == 333
    assert not any(row.get("event") == "OPTION_TOKEN_COVERAGE_BELOW_THRESHOLD" for row in capture.rows)
