from __future__ import annotations

import json
from datetime import datetime, timezone

import dashboard.streamlit_app_runtime as runtime
from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot


class _FakeColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}
        self.messages = []

    def columns(self, n):
        return [_FakeColumn() for _ in range(int(n))]

    def caption(self, message):
        self.messages.append(("caption", str(message)))

    def warning(self, message):
        self.messages.append(("warning", str(message)))

    def error(self, message):
        self.messages.append(("error", str(message)))

    def markdown(self, *args, **kwargs):
        return None

    def metric(self, *args, **kwargs):
        return None


def _snapshot_payload(*, market_open: bool = True) -> dict:
    return build_market_snapshot(
        generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        market_open=market_open,
        symbols_payload={
            "NIFTY": build_symbol_market_snapshot(
                spot=22500.0,
                ltp=22510.0,
                regime={"trend": "TREND", "volatility_state": "NORMAL", "confidence": 0.7},
                option_chain_summary={"atm_strike": 22500.0, "chain_quality": "OK"},
                feed_health={
                    "underlying_quote_age_sec": 0.5,
                    "option_quote_age_sec": 0.7,
                    "status": "OK",
                },
            )
        },
        warnings=[],
        compute_ms=3.0,
        loop_id="loop-1",
    )


def test_dashboard_snapshot_reader_returns_fresh_state_from_artifact(tmp_path):
    path = tmp_path / "market_snapshot_latest.json"
    path.write_text(json.dumps(_snapshot_payload()), encoding="utf-8")

    payload = runtime.read_market_snapshot_for_dashboard(path, stale_after_sec=999999.0)

    assert payload["state"] == "fresh"
    assert payload["snapshot"]["symbols"]["NIFTY"]["ltp"] == 22510.0


def test_missing_snapshot_returns_explicit_missing_state_no_recompute(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing.json"

    monkeypatch.setattr(runtime, "fetch_live_market_data", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fetch")))

    payload = runtime.read_market_snapshot_for_dashboard(missing_path)

    assert payload["state"] == "missing"
    assert payload["snapshot"] == {}


def test_malformed_snapshot_returns_invalid_state_no_recompute(tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text("{bad-json", encoding="utf-8")

    monkeypatch.setattr(runtime, "fetch_live_market_data", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not fetch")))

    payload = runtime.read_market_snapshot_for_dashboard(path)

    assert payload["state"] == "invalid"
    assert payload["snapshot"] == {}


def test_market_snapshot_render_does_not_call_forbidden_heavy_helpers(tmp_path, monkeypatch):
    fake_st = _FakeStreamlit()
    path = tmp_path / "market_snapshot_latest.json"
    path.write_text(json.dumps(_snapshot_payload(market_open=False)), encoding="utf-8")
    original_view_model = runtime.get_market_snapshot_view_model

    monkeypatch.setattr(runtime, "st", fake_st)
    monkeypatch.setattr(runtime, "get_market_snapshot_view_model", lambda: original_view_model(path))
    monkeypatch.setattr(runtime, "fetch_live_market_data", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fetch_live_market_data must not run")))
    monkeypatch.setattr("core.market_data._warm_seed_ohlc_from_history", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("warm seed must not run")))
    monkeypatch.setattr(runtime, "_is_ops_research_mode", lambda: False)

    runtime._render_market_snapshot()

    assert any("Snapshot:" in msg or "Market snapshot" in msg for _kind, msg in fake_st.messages)
