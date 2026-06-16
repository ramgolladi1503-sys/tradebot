from __future__ import annotations

import time
from types import SimpleNamespace

from config import config as cfg
from core.execution.execution_guard import evaluate_execution_guard
from core.execution_router import ExecutionRouter


def _snapshot(**overrides):
    payload = {
        "ts": time.time(),
        "bid": 100.0,
        "ask": 101.0,
    }
    payload.update(overrides)
    return payload


def _trade(trade_id: str = "T-GUARD-1"):
    return SimpleNamespace(
        trade_id=trade_id,
        symbol="NIFTY",
        instrument="OPT",
        instrument_id="NIFTY|2026-02-12|25200|CE",
        instrument_token=12345,
        side="BUY",
        entry_price=101.0,
        stop_loss=98.0,
        target=108.0,
        qty=10,
        confidence=0.8,
        tradable=True,
        tradable_reasons_blocking=[],
        order_type="LIMIT",
        expiry="2026-02-12",
        strike=25200,
        right="CE",
        exchange="NFO",
        product="MIS",
        timestamp_bucket=123456,
    )


def test_execution_guard_clean_tight_quote_passes():
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot=_snapshot(ts=now),
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
        reference_price=101.0,
    )
    assert decision.execution_allowed is True
    assert decision.execution_entry == 101.0
    assert decision.reasons == []


def test_execution_guard_future_timestamp_blocks_fail_closed():
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot=_snapshot(ts=now + 5.0),
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
    )
    assert decision.execution_allowed is False
    assert decision.execution_entry is None
    assert decision.reasons == ["future_quote_timestamp"]


def test_execution_guard_fallback_quote_is_not_executable():
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot=_snapshot(ts=now, quote_source="rest_fallback", fallback_used=True),
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
    )
    assert decision.execution_allowed is False
    assert "fallback_quote" in decision.reasons


def test_execution_guard_missing_depth_blocks_when_required():
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot=_snapshot(ts=now, require_depth=True, depth=None),
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
    )
    assert decision.execution_allowed is False
    assert "missing_depth" in decision.reasons


def test_execution_guard_stale_depth_blocks():
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot=_snapshot(
            ts=now,
            require_depth=True,
            depth={"buy": [{"price": 100.0}], "sell": [{"price": 101.0}]},
            depth_age_sec=10.0,
        ),
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
    )
    assert decision.execution_allowed is False
    assert "stale_depth" in decision.reasons


def test_execution_guard_blocks_instrument_token_mismatch():
    now = time.time()
    decision = evaluate_execution_guard(
        side="BUY",
        bid=100.0,
        ask=101.0,
        snapshot=_snapshot(
            ts=now,
            require_instrument_token=True,
            instrument_token=111,
            expected_instrument_token=222,
        ),
        evaluated_at_epoch=now,
        max_quote_age_sec=2.0,
        max_spread_pct=0.05,
    )
    assert decision.execution_allowed is False
    assert "instrument_token_mismatch" in decision.reasons


def test_router_never_calls_fill_simulator_when_guard_blocks(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "trades.db"), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "APPROVAL_REQUIRED_MODES", "", raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_ON_EXEC", False, raising=False)
    monkeypatch.setattr(cfg, "ENFORCE_READINESS_ON_EXECUTION", False, raising=False)
    monkeypatch.setattr(cfg, "READINESS_ENFORCE_PAPER", False, raising=False)

    router = ExecutionRouter()
    calls = {"count": 0}

    def _simulate(*args, **kwargs):
        del args, kwargs
        calls["count"] += 1
        return True, 101.0, {"fill_status": "FILLED"}

    monkeypatch.setattr(router.paper_sim, "simulate", _simulate)

    filled, price, report = router.execute(
        _trade("T-GUARD-BLOCKED"),
        bid=100.0,
        ask=101.0,
        volume=1000,
        snapshot_fn=lambda: _snapshot(require_depth=True, depth=None),
    )

    assert filled is False
    assert price is None
    assert report["reason_if_aborted"] == "missing_depth"
    assert calls["count"] == 0
