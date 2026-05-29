from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config import config as cfg
from core._engine_phase2_adapter_base import build_candidates_phase2
from core.trade_schema import Trade
from strategies.trade_builder import TradeBuilder


def _live_market_data(*, now_epoch: float, option_chain_row: dict) -> dict:
    return {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "execution_mode": "LIVE",
        "market_open": True,
        "timestamp": now_epoch,
        "timestamp_epoch": now_epoch,
        "ltp": 100.0,
        "option_chain": [option_chain_row],
    }


def _base_trade() -> Trade:
    return Trade(
        trade_id="T1",
        timestamp=datetime.fromtimestamp(1_000.0, tz=timezone.utc),
        symbol="NIFTY",
        instrument="OPT",
        instrument_token=123,
        strike=20000,
        expiry="2026-01-01",
        side="BUY",
        entry_price=10.0,
        stop_loss=8.0,
        target=14.0,
        qty=50,
        capital_at_risk=1000.0,
        expected_slippage=0.0,
        confidence=0.9,
        strategy="breakout",
        regime="TREND",
    )


def test_live_missing_quote_age_fails_closed(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    builder = TradeBuilder.__new__(TradeBuilder)
    trade = _base_trade()
    md = _live_market_data(
        now_epoch=1_000.0,
        option_chain_row={
            "instrument_token": 123,
            "tradingsymbol": "NIFTY26JAN20000CE",
            "strike": 20000,
            "type": "CE",
            "ltp": 10.0,
            "best_bid": 9.8,
            "best_ask": 10.2,
            "spread_pct": 0.002,
            "quote_ts_epoch": None,
            "quote_age_sec": None,
            "quote_source": "option_chain_live",
            "liquidity_score": 1.0,
        },
    )

    snapshot = builder._stamp_quote_truth_snapshot(trade, market_data=md, source_flags={}, lifecycle=None)
    assert snapshot.get("quote_age_sec") is None

    ranked = build_candidates_phase2([trade])
    assert ranked
    assert ranked[0].get("phase2_missing_quote_age_sec") is True
    assert ranked[0].get("execution_ok") is False


def test_live_quote_ts_derives_quote_age_sec(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    builder = TradeBuilder.__new__(TradeBuilder)
    trade = _base_trade()
    md = _live_market_data(
        now_epoch=1_000.0,
        option_chain_row={
            "instrument_token": 123,
            "tradingsymbol": "NIFTY26JAN20000CE",
            "strike": 20000,
            "type": "CE",
            "ltp": 10.0,
            "best_bid": 9.8,
            "best_ask": 10.2,
            "spread_pct": 0.002,
            "quote_ts_epoch": 995.0,
            "quote_source": "option_chain_live",
            "liquidity_score": 1.0,
        },
    )

    snapshot = builder._stamp_quote_truth_snapshot(trade, market_data=md, source_flags={}, lifecycle=None)
    assert snapshot.get("quote_age_sec") == pytest.approx(5.0)


def test_live_missing_bid_ask_fails_closed_for_spread_context(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    trade = _base_trade()
    # Provide quote age but no bid/ask -> spread_pct missing -> Phase2 blocks in LIVE.
    trade = trade  # frozen, will be stamped via quote truth snapshot
    builder = TradeBuilder.__new__(TradeBuilder)
    md = _live_market_data(
        now_epoch=1_000.0,
        option_chain_row={
            "instrument_token": 123,
            "tradingsymbol": "NIFTY26JAN20000CE",
            "strike": 20000,
            "type": "CE",
            "ltp": 10.0,
            "quote_ts_epoch": 999.0,
            "quote_source": "option_chain_live",
            "liquidity_score": 1.0,
        },
    )
    builder._stamp_quote_truth_snapshot(trade, market_data=md, source_flags={}, lifecycle=None)

    ranked = build_candidates_phase2([trade])
    assert ranked
    assert ranked[0].get("phase2_missing_spread_context") is True
    assert ranked[0].get("execution_ok") is False


def test_live_bid_ask_propagates_spread_pct_for_phase2(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    trade = _base_trade()
    builder = TradeBuilder.__new__(TradeBuilder)
    md = _live_market_data(
        now_epoch=1_000.0,
        option_chain_row={
            "instrument_token": 123,
            "tradingsymbol": "NIFTY26JAN20000CE",
            "strike": 20000,
            "type": "CE",
            "ltp": 10.0,
            "best_bid": 9.8,
            "best_ask": 10.2,
            "spread_pct": 0.002,
            "quote_ts_epoch": 999.0,
            "quote_source": "option_chain_live",
            "liquidity_score": 1.0,
        },
    )
    snapshot = builder._stamp_quote_truth_snapshot(trade, market_data=md, source_flags={}, lifecycle=None)
    assert snapshot.get("spread_pct") is not None

    ranked = build_candidates_phase2([trade])
    assert ranked
    assert ranked[0].get("phase2_missing_spread_context") is not True


def test_live_unknown_quote_source_stays_blocked(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    trade = _base_trade()
    builder = TradeBuilder.__new__(TradeBuilder)
    md = _live_market_data(
        now_epoch=1_000.0,
        option_chain_row={
            "instrument_token": 123,
            "tradingsymbol": "NIFTY26JAN20000CE",
            "strike": 20000,
            "type": "CE",
            "ltp": 10.0,
            "best_bid": 9.8,
            "best_ask": 10.2,
            "spread_pct": 0.002,
            "quote_ts_epoch": 999.0,
            "quote_source": "unknown",
            "liquidity_score": 1.0,
        },
    )
    builder._stamp_quote_truth_snapshot(trade, market_data=md, source_flags={}, lifecycle=None)

    ranked = build_candidates_phase2([trade])
    # In LIVE strict mode, unknown quote source is a hard drop (fail-closed).
    assert ranked == []
