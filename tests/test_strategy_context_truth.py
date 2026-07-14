from __future__ import annotations

import socket
import threading

import pytest

from core.candidate_pool_orchestrator import build_candidate_pool_report, get_default_candidate_generators
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.orchestrator import _snapshot_symbol_payload
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
import strategies.strategy_registry as strategy_registry


def _regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.8,
            "TREND_DOWN": 0.0,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.8,
            "VOLATILITY_EXPANSION": 0.45,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
    )


def _full_truth_snapshot() -> dict:
    return {
        "spot": 22620.0,
        "ltp": 22620.0,
        "metadata": {
            "previous_spot_ltp": 22590.0,
            "strategy_context_truth": {
                "ts_epoch": 1721028600.0,
                "vwap": 22540.0,
                "orb_high": 22600.0,
                "orb_low": 22460.0,
                "atr": 70.0,
                "range_width_pct": 0.14,
                "atr_short": 35.0,
                "atr_long": 100.0,
                "volume_z": 1.5,
                "vwap_slope": 0.03,
                "minutes_since_open": 35,
                "minutes_to_close": 280,
                "open_price": 22500.0,
                "day_high": 22620.0,
                "day_low": 22460.0,
                "nearest_support": 22590.0,
                "nearest_resistance": 22600.0,
                "option_ce_ltp": 120.0,
                "option_pe_ltp": 90.0,
                "ce_premium_change": 12.0,
                "pe_premium_change": 0.0,
                "ce_spread_pct": 0.8,
                "pe_spread_pct": 0.8,
                "ce_depth": 1200.0,
                "pe_depth": 1200.0,
                "option_ltp_age_sec": 0.4,
                "quote_source": "live_option_tick",
                "fallback_used": False,
            },
            "strategy_context_provenance": {
                "vwap": {"source_component": "unit", "source_field": "vwap", "status": "TRUTHFUL"},
            },
            "strategy_context_missing": {},
        },
    }


def _direct_context() -> StrategyContext:
    return StrategyContext(
        symbol="NIFTY",
        ts_epoch=1721028600.0,
        spot_ltp=22620.0,
        open_price=22500.0,
        vwap=22540.0,
        day_high=22620.0,
        day_low=22460.0,
        nearest_support=22590.0,
        nearest_resistance=22600.0,
        orb_high=22600.0,
        orb_low=22460.0,
        range_width_pct=0.14,
        atr=70.0,
        atr_short=35.0,
        atr_long=100.0,
        volume_z=1.5,
        vwap_slope=0.03,
        option_ce_ltp=120.0,
        option_pe_ltp=90.0,
        ce_premium_change=12.0,
        pe_premium_change=0.0,
        ce_spread_pct=0.8,
        pe_spread_pct=0.8,
        ce_depth=1200.0,
        pe_depth=1200.0,
        option_ltp_age_sec=0.4,
        quote_source="live_option_tick",
        fallback_used=False,
        minutes_since_open=35,
        minutes_to_close=280,
        metadata={"previous_spot_ltp": 22590.0},
    )


def _fingerprint(ctx: StrategyContext) -> list[tuple[str, float, str, str]]:
    report = build_candidate_pool_report(
        ctx,
        _regime(),
        candidate_generators=get_default_candidate_generators(),
    )
    return [
        (candidate.strategy_id, round(candidate.raw_score, 6), candidate.direction, candidate.status)
        for candidate in report.candidates
        if candidate.direction in {"BUY_CALL", "BUY_PUT"}
    ]


def test_vwap_uses_truthful_value_not_candle_close():
    ctx = _strategy_context_from_market_symbol(
        "NIFTY",
        {
            "spot": 22620.0,
            "ltp": 22620.0,
            "ohlc": {"open": 22550.0, "high": 22650.0, "low": 22520.0, "close": 22610.0},
            "metadata": {
                "strategy_context_truth": {"vwap": 22540.0},
                "strategy_context_provenance": {"vwap": {"source_field": "vwap"}},
                "strategy_context_missing": {},
            },
        },
    )

    assert ctx.vwap == 22540.0
    assert ctx.vwap != 22610.0


def test_missing_vwap_stays_missing_and_close_is_not_fallback():
    ctx = _strategy_context_from_market_symbol(
        "NIFTY",
        {
            "spot": 22620.0,
            "ltp": 22620.0,
            "ohlc": {"open": 22550.0, "high": 22650.0, "low": 22520.0, "close": 22610.0},
            "metadata": {
                "strategy_context_truth": {},
                "strategy_context_provenance": {},
                "strategy_context_missing": {"vwap": {"status": "MISSING_SOURCE"}},
            },
        },
    )

    assert ctx.vwap is None
    assert ctx.metadata["strategy_context_missing"]["vwap"]["status"] == "MISSING_SOURCE"


def test_session_open_and_day_range_do_not_use_current_candle_substitutes():
    ctx = _strategy_context_from_market_symbol(
        "NIFTY",
        {
            "spot": 22620.0,
            "ltp": 22620.0,
            "ohlc": {"open": 22550.0, "high": 22650.0, "low": 22520.0, "close": 22610.0},
            "metadata": {
                "strategy_context_truth": {},
                "strategy_context_provenance": {},
                "strategy_context_missing": {
                    "open_price": {"status": "MISSING_SOURCE"},
                    "day_high": {"status": "MISSING_SOURCE"},
                    "day_low": {"status": "MISSING_SOURCE"},
                },
            },
        },
    )

    assert ctx.open_price is None
    assert ctx.day_high is None
    assert ctx.day_low is None


def test_snapshot_payload_carries_truthful_orb_only_after_completion():
    warnings: list[str] = []
    payload = _snapshot_symbol_payload(
        {
            "symbol": "NIFTY",
            "spot": 22620.0,
            "ltp": 22620.0,
            "vwap": 22540.0,
            "atr": 70.0,
            "vol_z": 1.5,
            "vwap_slope": 0.03,
            "minutes_since_open": 35,
            "market_open": True,
            "segment": "NSE_FNO",
            "timestamp_ist": "2026-07-14T10:15:00+05:30",
            "ltp_ts_epoch": 1721028600.0,
            "orb_high": 22600.0,
            "orb_low": 22460.0,
            "orb_state": {"status": "NEUTRAL"},
            "option_chain_health": {"quote_age_sec": 0.4},
            "quote_source": "live_option_tick",
        },
        warnings,
    )

    truth = payload["metadata"]["strategy_context_truth"]
    missing = payload["metadata"]["strategy_context_missing"]

    assert truth["orb_high"] == 22600.0
    assert truth["orb_low"] == 22460.0
    assert truth["minutes_to_close"] == 315
    assert "day_high" in missing
    assert "open_price" in missing


def test_pending_orb_does_not_become_context_values():
    warnings: list[str] = []
    payload = _snapshot_symbol_payload(
        {
            "symbol": "NIFTY",
            "spot": 22620.0,
            "ltp": 22620.0,
            "vwap": 22540.0,
            "atr": 70.0,
            "vol_z": 1.5,
            "vwap_slope": 0.03,
            "minutes_since_open": 5,
            "market_open": True,
            "segment": "NSE_FNO",
            "timestamp_ist": "2026-07-14T09:20:00+05:30",
            "ltp_ts_epoch": 1721025000.0,
            "orb_high": 22600.0,
            "orb_low": 22460.0,
            "orb_state": {"status": "PENDING"},
            "option_chain_health": {"quote_age_sec": 0.4},
            "quote_source": "live_option_tick",
        },
        warnings,
    )
    ctx = _strategy_context_from_market_symbol("NIFTY", payload)

    assert ctx.orb_high is None
    assert ctx.orb_low is None
    assert ctx.metadata["strategy_context_missing"]["orb_high"]["status"] == "INCOMPLETE"
    assert ctx.metadata["strategy_context_missing"]["orb_low"]["status"] == "INCOMPLETE"


def test_atr_short_and_long_are_not_synthesized_from_single_atr():
    ctx = _strategy_context_from_market_symbol(
        "NIFTY",
        {
            "spot": 22620.0,
            "ltp": 22620.0,
            "metadata": {
                "strategy_context_truth": {"atr": 70.0},
                "strategy_context_provenance": {"atr": {"timeframe": "1m", "lookback": "ATR_PERIOD"}},
                "strategy_context_missing": {
                    "atr_short": {"status": "MISSING_SOURCE"},
                    "atr_long": {"status": "MISSING_SOURCE"},
                },
            },
        },
    )

    assert ctx.atr == 70.0
    assert ctx.atr_short is None
    assert ctx.atr_long is None


def test_option_evidence_and_previous_spot_propagate_from_runtime_rows():
    warnings: list[str] = []
    payload = _snapshot_symbol_payload(
        {
            "symbol": "NIFTY",
            "spot": 22620.0,
            "ltp": 22620.0,
            "prev_ltp": 22590.0,
            "vwap": 22540.0,
            "atr": 70.0,
            "vol_z": 1.5,
            "vwap_slope": 0.03,
            "minutes_since_open": 35,
            "market_open": True,
            "segment": "NSE_FNO",
            "timestamp_ist": "2026-07-14T10:15:00+05:30",
            "ltp_ts_epoch": 1721028600.0,
            "orb_high": 22600.0,
            "orb_low": 22460.0,
            "orb_state": {"status": "NEUTRAL"},
            "option_chain_health": {"quote_age_sec": 0.4},
            "quote_source": "live_option_tick",
            "option_chain": [
                {"strike": 22600.0, "type": "CE", "ltp": 120.0, "spread_pct": 0.8, "bid_qty": 600.0, "ask_qty": 600.0, "ltp_change": 12.0},
                {"strike": 22600.0, "type": "PE", "ltp": 90.0, "spread_pct": 0.8, "bid_qty": 600.0, "ask_qty": 600.0, "ltp_change": 0.0},
            ],
        },
        warnings,
    )
    ctx = _strategy_context_from_market_symbol("NIFTY", payload)

    assert ctx.option_ce_ltp == 120.0
    assert ctx.option_pe_ltp == 90.0
    assert ctx.ce_premium_change == 12.0
    assert ctx.pe_premium_change == 0.0
    assert ctx.ce_spread_pct == 0.8
    assert ctx.pe_spread_pct == 0.8
    assert ctx.ce_depth == 1200.0
    assert ctx.pe_depth == 1200.0
    assert ctx.option_ltp_age_sec == 0.4
    assert ctx.metadata["previous_spot_ltp"] == 22590.0


def test_direct_context_fingerprint_is_unchanged():
    assert _fingerprint(_direct_context()) == [
        ("opening_range_retest_v1", 0.639513, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("compression_breakout_v1", 0.675169, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("trend_pullback_v1", 0.719646, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("option_pressure_confirmation_v1", 0.81475, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]


def test_runtime_adapter_matches_direct_context_when_truth_is_complete():
    ctx = _strategy_context_from_market_symbol("NIFTY", _full_truth_snapshot())

    assert _fingerprint(ctx) == [
        ("opening_range_retest_v1", 0.639513, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("compression_breakout_v1", 0.675169, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("trend_pullback_v1", 0.719646, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("option_pressure_confirmation_v1", 0.81475, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]


def test_runtime_context_construction_opens_no_network_or_threads(monkeypatch: pytest.MonkeyPatch):
    thread_starts: list[str] = []

    def _fail_connection(*_args, **_kwargs):
        raise AssertionError("runtime context construction must not open network connections")

    original_thread_start = threading.Thread.start

    def _record_thread_start(self: threading.Thread):
        thread_starts.append(self.name)
        raise AssertionError("runtime context construction must not start threads")

    monkeypatch.setattr(socket, "create_connection", _fail_connection)
    monkeypatch.setattr(threading.Thread, "start", _record_thread_start)

    try:
        _strategy_context_from_market_symbol("NIFTY", _full_truth_snapshot())
    finally:
        monkeypatch.setattr(threading.Thread, "start", original_thread_start)

    assert thread_starts == []


def test_runtime_context_construction_does_not_call_source_parsing(monkeypatch: pytest.MonkeyPatch):
    def _fail(*_args, **_kwargs):
        raise AssertionError("source parsing must stay offline only")

    monkeypatch.setattr(strategy_registry, "_extract_embedded_profile_defaults", _fail)

    ctx = _strategy_context_from_market_symbol("NIFTY", _full_truth_snapshot())

    assert ctx.symbol == "NIFTY"
