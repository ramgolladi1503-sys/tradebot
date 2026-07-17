from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import core.market_data as market_data
from core.orchestrator import _strategy_context_snapshot_metadata
from core.ranking_orchestrator import build_ranked_opportunity_report
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from core.market_data import check_market_data_time_sanity
from core.session_bar_history import (
    build_session_bar_history_state,
    calculate_session_range_width_pct,
    calculate_session_range_width_pct_from_completed_history,
)
from strategies.movement.compression_breakout import _compression_evidence_score, generate_compression_breakout_candidates
from tests.test_candidate_phase2_ownership import _full_context, _regime


IST = ZoneInfo("Asia/Kolkata")


def _completed_history(*, include_future_bar: bool = False) -> list[dict[str, object]]:
    session_date = "2026-07-14"
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    bars: list[dict[str, object]] = [
        {
            "symbol": "NIFTY",
            "session_date": session_date,
            "timeframe": "1m",
            "bar_start_timestamp": start.isoformat(),
            "bar_end_timestamp": (start + timedelta(minutes=1)).isoformat(),
            "open": 100.0,
            "high": 112.0,
            "low": 98.0,
            "close": 100.0,
            "volume": 1000.0,
            "source": "unit_test",
            "source_timestamp": (start + timedelta(minutes=1)).isoformat(),
            "receipt_timestamp": (start + timedelta(minutes=1, seconds=1)).isoformat(),
            "is_complete": True,
        },
        {
            "symbol": "NIFTY",
            "session_date": session_date,
            "timeframe": "1m",
            "bar_start_timestamp": (start + timedelta(minutes=1)).isoformat(),
            "bar_end_timestamp": (start + timedelta(minutes=2)).isoformat(),
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1100.0,
            "source": "unit_test",
            "source_timestamp": (start + timedelta(minutes=2)).isoformat(),
            "receipt_timestamp": (start + timedelta(minutes=2, seconds=1)).isoformat(),
            "is_complete": True,
        },
    ]
    if include_future_bar:
        bars.append(
            {
                "symbol": "NIFTY",
                "session_date": session_date,
                "timeframe": "1m",
                "bar_start_timestamp": (start + timedelta(minutes=2)).isoformat(),
                "bar_end_timestamp": (start + timedelta(minutes=3)).isoformat(),
                "open": 100.0,
                "high": 400.0,
                "low": 1.0,
                "close": 200.0,
                "volume": 1200.0,
                "source": "unit_test",
                "source_timestamp": (start + timedelta(minutes=3)).isoformat(),
                "receipt_timestamp": (start + timedelta(minutes=3, seconds=1)).isoformat(),
                "is_complete": True,
            }
        )
    return bars


def _session_state(*, include_future_bar: bool = False):
    cutoff = datetime(2026, 7, 14, 9, 17, tzinfo=IST)
    return build_session_bar_history_state(
        symbol="NIFTY",
        bars=_completed_history(include_future_bar=include_future_bar),
        cutoff_timestamp=cutoff,
        segment="DEFAULT",
        source="unit_test",
        timeframe="1m",
        receipt_timestamp=cutoff + timedelta(seconds=1),
    )


def _runtime_market_data(*, range_width_pct: float | None, completed_bar_history: list[dict[str, object]]) -> dict[str, object]:
    return {
        "symbol": "NIFTY",
        "spot": 22620.0,
        "ltp": 22620.0,
        "prev_ltp": 22590.0,
        "open_price": 22500.0,
        "vwap": 22540.0,
        "atr": 70.0,
        "atr_short": 35.0,
        "atr_long": 100.0,
        "volume_z": 1.5,
        "vwap_slope": 0.03,
        "day_high": 22620.0,
        "day_low": 22460.0,
        "nearest_support": 22590.0,
        "nearest_resistance": 22600.0,
        "orb_high": 22600.0,
        "orb_low": 22460.0,
        "range_width_pct": range_width_pct,
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
        "minutes_since_open": 35,
        "minutes_to_close": 280,
        "completed_bar_history": completed_bar_history,
    }


def _runtime_context(*, range_width_pct: float | None, completed_bar_history: list[dict[str, object]]):
    market_data = _runtime_market_data(range_width_pct=range_width_pct, completed_bar_history=completed_bar_history)
    market_data["metadata"] = _strategy_context_snapshot_metadata(market_data)
    return _strategy_context_from_market_symbol("NIFTY", market_data)


def _fingerprint(report) -> list[tuple[str, float, str, str]]:
    return [
        (candidate.strategy_id, round(candidate.raw_score, 6), candidate.direction, candidate.status)
        for candidate in report.candidate_pool.candidates
        if candidate.direction in {"BUY_CALL", "BUY_PUT"}
    ]


def test_range_width_pct_is_calculated_from_completed_session_range():
    session_state = _session_state()
    assert calculate_session_range_width_pct(
        day_high=session_state.day_high,
        day_low=session_state.day_low,
        reference_price=100.0,
    ) == pytest.approx(0.14)


def test_forming_bar_is_excluded_from_range_width_and_candidate_identity():
    session_state = _session_state()
    future_session_state = _session_state(include_future_bar=True)
    assert future_session_state.day_high == session_state.day_high
    assert future_session_state.day_low == session_state.day_low

    runtime_report = build_ranked_opportunity_report(
        _runtime_context(
            range_width_pct=calculate_session_range_width_pct(
                day_high=session_state.day_high,
                day_low=session_state.day_low,
                reference_price=100.0,
            ),
            completed_bar_history=session_state.history_payload(),
        ),
        _regime(),
        candidate_generators=(generate_compression_breakout_candidates,),
        include_no_trade_candidate=False,
    )

    assert _fingerprint(runtime_report) == [("compression_breakout_v1", 0.470676, "BUY_CALL", "VALIDATED_CANDIDATE")]
    assert runtime_report.top_rank_strategy_id == "compression_breakout_v1"


def test_runtime_uses_latest_completed_close_not_live_ltp(monkeypatch):
    fixed_now = datetime(2026, 7, 14, 9, 17, tzinfo=IST)
    bars = _completed_history()
    latest_close = float(bars[-1]["close"])
    live_ltp = 101.0

    class _DummyRegimeModel:
        def predict(self, _features):
            return {
                "primary_regime": "TREND",
                "regime_probs": {"TREND": 0.8, "RANGE": 0.2},
                "regime_entropy": 0.2,
                "unstable_regime_flag": False,
            }

    monkeypatch.setattr(market_data.cfg, "SYMBOLS", ["NIFTY"], raising=False)
    monkeypatch.setattr(market_data.cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(market_data.cfg, "REQUIRE_LIVE_QUOTES", False, raising=False)
    monkeypatch.setattr(market_data.cfg, "ALLOW_SYNTHETIC_CHAIN", False, raising=False)
    monkeypatch.setattr(market_data, "now_ist", lambda: fixed_now)
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: fixed_now.timestamp())
    monkeypatch.setattr(market_data, "is_open", lambda now_dt=None, segment=None: True)
    monkeypatch.setattr(market_data, "check_market_data_time_sanity", lambda **kwargs: {"ok": True, "reasons": []})
    monkeypatch.setattr(market_data, "_REGIME_MODEL", _DummyRegimeModel(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_CAL", type("NewsCal", (), {"get_shock": lambda self: {}})(), raising=False)
    monkeypatch.setattr(market_data, "_NEWS_TEXT", type("NewsText", (), {"encode": lambda self: {}})(), raising=False)
    monkeypatch.setattr(
        market_data,
        "_CROSS_ASSET",
        type("CrossAsset", (), {"update": lambda self, *_args, **_kwargs: {"features": {}, "data_quality": {}}})(),
        raising=False,
    )
    monkeypatch.setattr(market_data, "fetch_option_chain", lambda *_args, **_kwargs: [])

    def _fake_get_ltp(symbol: str):
        market_data._DATA_CACHE.setdefault(symbol, {})
        market_data._DATA_CACHE[symbol]["ltp_source"] = "live"
        market_data._DATA_CACHE[symbol]["ltp_ts_epoch"] = fixed_now.timestamp()
        return live_ltp

    monkeypatch.setattr(market_data, "get_ltp", _fake_get_ltp)
    monkeypatch.setattr(
        market_data.ohlc_buffer,
        "get_completed_bars",
        lambda symbol, *, as_of, interval_seconds=60: list(bars),
    )
    monkeypatch.setattr(
        market_data,
        "compute_indicators",
        lambda bars, **kwargs: {
            "vwap": latest_close,
            "atr": 50.0,
            "adx": 25.0,
            "vol_z": 0.2,
            "vwap_slope": 0.1,
            "last_ts": fixed_now,
            "ok": True,
        },
    )

    rows = market_data.fetch_live_market_data(allow_history_seed=False)
    snap = next(row for row in rows if row.get("symbol") == "NIFTY" and row.get("instrument") == "OPT")

    expected = calculate_session_range_width_pct_from_completed_history(
        symbol="NIFTY",
        bars=bars,
        cutoff_timestamp=fixed_now,
        segment="DEFAULT",
        reference_price=latest_close,
    )

    assert snap["range_width_pct"] == pytest.approx(expected)
    assert snap["range_width_pct"] == pytest.approx((112.0 - 98.0) / 100.0)
    assert snap["range_width_pct"] != pytest.approx((112.0 - 98.0) / live_ltp)
    assert snap["range_width_pct_provenance"]["reference_price_source"] == "latest_completed_close"
    assert snap["range_width_pct_provenance"]["reference_price"] == pytest.approx(latest_close)
    assert snap["valid"] is True


def test_new_completed_bar_updates_denominator_only_after_completion():
    session_state = _session_state()
    base_width = calculate_session_range_width_pct_from_completed_history(
        symbol="NIFTY",
        bars=session_state.history_payload(),
        cutoff_timestamp=datetime(2026, 7, 14, 9, 17, tzinfo=IST),
        segment="DEFAULT",
        reference_price=session_state.history_payload()[-1]["close"],
    )
    later_state = build_session_bar_history_state(
        symbol="NIFTY",
        bars=_completed_history(include_future_bar=True),
        cutoff_timestamp=datetime(2026, 7, 14, 9, 18, tzinfo=IST),
        segment="DEFAULT",
        source="unit_test",
        timeframe="1m",
        receipt_timestamp=datetime(2026, 7, 14, 9, 18, 1, tzinfo=IST),
    )
    later_width = calculate_session_range_width_pct_from_completed_history(
        symbol="NIFTY",
        bars=later_state.history_payload(),
        cutoff_timestamp=datetime(2026, 7, 14, 9, 18, tzinfo=IST),
        segment="DEFAULT",
        reference_price=later_state.history_payload()[-1]["close"],
    )

    assert base_width == pytest.approx((112.0 - 98.0) / 100.0)
    assert later_width is not None
    assert later_width != base_width


def test_missing_completed_close_fails_closed():
    session_state = _session_state()
    assert (
        calculate_session_range_width_pct_from_completed_history(
            symbol="NIFTY",
            bars=session_state.history_payload(),
            cutoff_timestamp=datetime(2026, 7, 14, 9, 15, tzinfo=IST),
            segment="DEFAULT",
            reference_price=100.0,
        )
        is None
    )


def test_future_mutation_and_physical_truncation_do_not_change_range_width():
    base_state = _session_state()
    future_state = _session_state(include_future_bar=True)
    truncated_state = build_session_bar_history_state(
        symbol="NIFTY",
        bars=_completed_history(include_future_bar=False),
        cutoff_timestamp=datetime(2026, 7, 14, 9, 17, tzinfo=IST),
        segment="DEFAULT",
        source="unit_test",
        timeframe="1m",
        receipt_timestamp=datetime(2026, 7, 14, 9, 17, 1, tzinfo=IST),
    )

    base_width = calculate_session_range_width_pct(day_high=base_state.day_high, day_low=base_state.day_low, reference_price=100.0)
    future_width = calculate_session_range_width_pct(day_high=future_state.day_high, day_low=future_state.day_low, reference_price=100.0)
    truncated_width = calculate_session_range_width_pct(day_high=truncated_state.day_high, day_low=truncated_state.day_low, reference_price=100.0)

    assert future_width == base_width
    assert truncated_width == base_width


def test_mixed_symbol_and_mixed_session_history_fail_closed():
    mixed_symbol = _completed_history()
    mixed_symbol.append(
        {
            "symbol": "RELIANCE",
            "session_date": "2026-07-14",
            "timeframe": "1m",
            "bar_start_timestamp": datetime(2026, 7, 14, 9, 17, tzinfo=IST).isoformat(),
            "bar_end_timestamp": datetime(2026, 7, 14, 9, 18, tzinfo=IST).isoformat(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
            "source": "unit_test",
            "source_timestamp": datetime(2026, 7, 14, 9, 18, tzinfo=IST).isoformat(),
            "receipt_timestamp": datetime(2026, 7, 14, 9, 18, 1, tzinfo=IST).isoformat(),
            "is_complete": True,
        }
    )
    assert (
        calculate_session_range_width_pct_from_completed_history(
            symbol="NIFTY",
            bars=mixed_symbol,
            cutoff_timestamp=datetime(2026, 7, 14, 9, 18, tzinfo=IST),
            segment="DEFAULT",
            reference_price=100.0,
        )
        is None
    )

    mixed_session = _completed_history()
    mixed_session.append(
        {
            "symbol": "NIFTY",
            "session_date": "2026-07-15",
            "timeframe": "1m",
            "bar_start_timestamp": datetime(2026, 7, 14, 9, 17, tzinfo=IST).isoformat(),
            "bar_end_timestamp": datetime(2026, 7, 14, 9, 18, tzinfo=IST).isoformat(),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
            "source": "unit_test",
            "source_timestamp": datetime(2026, 7, 14, 9, 18, tzinfo=IST).isoformat(),
            "receipt_timestamp": datetime(2026, 7, 14, 9, 18, 1, tzinfo=IST).isoformat(),
            "is_complete": True,
        }
    )
    assert (
        calculate_session_range_width_pct_from_completed_history(
            symbol="NIFTY",
            bars=mixed_session,
            cutoff_timestamp=datetime(2026, 7, 14, 9, 18, tzinfo=IST),
            segment="DEFAULT",
            reference_price=100.0,
        )
        is None
    )


@pytest.mark.parametrize(
    "bars, match",
    [
        (
            [
                {
                    "symbol": "NIFTY",
                    "session_date": "2026-07-14",
                    "timeframe": "1m",
                    "bar_start_timestamp": datetime(2026, 7, 14, 9, 15, tzinfo=IST).isoformat(),
                    "bar_end_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "open": 100.0,
                    "high": 90.0,
                    "low": 98.0,
                    "close": 100.0,
                    "volume": 1000.0,
                    "source": "unit_test",
                    "source_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "receipt_timestamp": datetime(2026, 7, 14, 9, 16, 1, tzinfo=IST).isoformat(),
                    "is_complete": True,
                }
            ],
            "invalid_ohlc_high",
        ),
        (
            [
                {
                    "symbol": "NIFTY",
                    "session_date": "2026-07-14",
                    "timeframe": "1m",
                    "bar_start_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "bar_end_timestamp": datetime(2026, 7, 14, 9, 17, tzinfo=IST).isoformat(),
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000.0,
                    "source": "unit_test",
                    "source_timestamp": datetime(2026, 7, 14, 9, 17, tzinfo=IST).isoformat(),
                    "receipt_timestamp": datetime(2026, 7, 14, 9, 17, 1, tzinfo=IST).isoformat(),
                    "is_complete": True,
                },
                {
                    "symbol": "NIFTY",
                    "session_date": "2026-07-14",
                    "timeframe": "1m",
                    "bar_start_timestamp": datetime(2026, 7, 14, 9, 15, tzinfo=IST).isoformat(),
                    "bar_end_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000.0,
                    "source": "unit_test",
                    "source_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "receipt_timestamp": datetime(2026, 7, 14, 9, 16, 1, tzinfo=IST).isoformat(),
                    "is_complete": True,
                },
            ],
            "out_of_order_bar",
        ),
        (
            [
                {
                    "symbol": "NIFTY",
                    "session_date": "2026-07-14",
                    "timeframe": "1m",
                    "bar_start_timestamp": datetime(2026, 7, 14, 9, 15, tzinfo=IST).isoformat(),
                    "bar_end_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "open": "bad",
                    "high": 102.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000.0,
                    "source": "unit_test",
                    "source_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "receipt_timestamp": datetime(2026, 7, 14, 9, 16, 1, tzinfo=IST).isoformat(),
                    "is_complete": True,
                }
            ],
            "invalid_price:open",
        ),
        (
            [
                {
                    "symbol": "NIFTY",
                    "session_date": "2026-07-14",
                    "timeframe": "1m",
                    "bar_start_timestamp": datetime(2026, 7, 14, 9, 15, tzinfo=IST).isoformat(),
                    "bar_end_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "open": 100.0,
                    "high": 102.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000.0,
                    "source": "unit_test",
                    "source_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "receipt_timestamp": datetime(2026, 7, 14, 9, 16, 1, tzinfo=IST).isoformat(),
                    "is_complete": True,
                },
                {
                    "symbol": "NIFTY",
                    "session_date": "2026-07-14",
                    "timeframe": "1m",
                    "bar_start_timestamp": datetime(2026, 7, 14, 9, 15, tzinfo=IST).isoformat(),
                    "bar_end_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "open": 100.0,
                    "high": 103.0,
                    "low": 98.0,
                    "close": 100.0,
                    "volume": 1000.0,
                    "source": "unit_test",
                    "source_timestamp": datetime(2026, 7, 14, 9, 16, tzinfo=IST).isoformat(),
                    "receipt_timestamp": datetime(2026, 7, 14, 9, 16, 1, tzinfo=IST).isoformat(),
                    "is_complete": True,
                },
            ],
            "duplicate_bar_timestamp",
        ),
    ],
)
def test_malformed_history_fails_closed(bars, match):
    assert (
        calculate_session_range_width_pct_from_completed_history(
            symbol="NIFTY",
            bars=bars,
            cutoff_timestamp=datetime(2026, 7, 14, 9, 18, tzinfo=IST),
            segment="DEFAULT",
            reference_price=100.0,
        )
        is None
    )


def test_runtime_propagation_matches_direct_candidate_fingerprint():
    session_state = _session_state()
    range_width = calculate_session_range_width_pct(
        day_high=session_state.day_high,
        day_low=session_state.day_low,
        reference_price=100.0,
    )
    market_data = _runtime_market_data(
        range_width_pct=range_width,
        completed_bar_history=session_state.history_payload(),
    )
    market_data["metadata"] = {
        "strategy_context_truth": {
            "range_width_pct": range_width,
            "completed_bar_history": session_state.history_payload(),
        },
        "strategy_context_provenance": {
            "range_width_pct": {
                "status": "TRUTHFUL",
                "source_component": "core.session_bar_history.calculate_session_range_width_pct",
                "source_field": "range_width_pct",
                "source_event_timestamp": session_state.latest_completed_timestamp,
                "receipt_timestamp": session_state.latest_completed_timestamp,
                "scope": "session_completed_bar",
                "complete": True,
                "timeframe": "1m",
                "symbol": session_state.symbol,
                "session_date": session_state.session_date,
            },
            "completed_bar_history": session_state.provenance_payload(
                source_component="core.session_bar_history.build_session_bar_history_state",
                receipt_timestamp=session_state.latest_completed_timestamp,
            ),
        },
        "strategy_context_missing": {},
    }
    runtime_ctx = _strategy_context_from_market_symbol("NIFTY", market_data)
    runtime_report = build_ranked_opportunity_report(
        runtime_ctx,
        _regime(),
        candidate_generators=(generate_compression_breakout_candidates,),
        include_no_trade_candidate=False,
    )

    direct_report = build_ranked_opportunity_report(
        _full_context(),
        _regime(),
        candidate_generators=(generate_compression_breakout_candidates,),
        include_no_trade_candidate=False,
    )

    assert runtime_ctx.range_width_pct == pytest.approx(0.14)
    assert runtime_ctx.metadata["strategy_context_provenance"]["range_width_pct"]["source_component"] == (
        "core.session_bar_history.calculate_session_range_width_pct"
    )
    assert _fingerprint(runtime_report) == [("compression_breakout_v1", 0.470676, "BUY_CALL", "VALIDATED_CANDIDATE")]
    assert _fingerprint(runtime_report) == _fingerprint(direct_report)
    assert runtime_report.top_rank_strategy_id == "compression_breakout_v1"


def test_runtime_and_replay_denominators_can_straddle_the_acceptance_gate():
    session_state = _session_state()
    close_width = calculate_session_range_width_pct(
        day_high=session_state.day_high,
        day_low=session_state.day_low,
        reference_price=100.0,
    )
    live_width = calculate_session_range_width_pct(
        day_high=session_state.day_high,
        day_low=session_state.day_low,
        reference_price=40.0,
    )

    assert close_width == pytest.approx(0.14)
    assert live_width == pytest.approx(0.35)
    assert close_width != live_width

    close_report = build_ranked_opportunity_report(
        _runtime_context(
            range_width_pct=close_width,
            completed_bar_history=session_state.history_payload(),
        ),
        _regime(COMPRESSION=0.5),
        candidate_generators=(generate_compression_breakout_candidates,),
        include_no_trade_candidate=False,
    )
    live_report = build_ranked_opportunity_report(
        _runtime_context(
            range_width_pct=live_width,
            completed_bar_history=session_state.history_payload(),
        ),
        _regime(COMPRESSION=0.5),
        candidate_generators=(generate_compression_breakout_candidates,),
        include_no_trade_candidate=False,
    )

    close_fingerprint = _fingerprint(close_report)
    live_fingerprint = _fingerprint(live_report)
    close_compression_score = _compression_evidence_score(
        _runtime_context(
            range_width_pct=close_width,
            completed_bar_history=session_state.history_payload(),
        ),
        _regime(COMPRESSION=0.5),
        {
            "MAX_ATR_RATIO": 0.75,
            "MAX_RANGE_WIDTH_PCT": 0.35,
            "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
            "MIN_COMPRESSION_SCORE": 0.5,
            "MIN_VWAP_ALIGNMENT_PCT": 0.0004,
        },
    )
    live_compression_score = _compression_evidence_score(
        _runtime_context(
            range_width_pct=live_width,
            completed_bar_history=session_state.history_payload(),
        ),
        _regime(COMPRESSION=0.5),
        {
            "MAX_ATR_RATIO": 0.75,
            "MAX_RANGE_WIDTH_PCT": 0.35,
            "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
            "MIN_COMPRESSION_SCORE": 0.5,
            "MIN_VWAP_ALIGNMENT_PCT": 0.0004,
        },
    )

    assert close_fingerprint == [("compression_breakout_v1", close_fingerprint[0][1], "BUY_CALL", "VALIDATED_CANDIDATE")]
    assert close_report.top_rank_strategy_id == "compression_breakout_v1"
    assert close_compression_score > 0.5
    assert live_compression_score < 0.5
    assert live_fingerprint == []
    assert live_report.top_rank_strategy_id is None


def test_stale_runtime_ltp_fails_closed():
    now_epoch = datetime(2026, 7, 14, 9, 30, tzinfo=IST).timestamp()
    verdict = check_market_data_time_sanity(
        ltp_ts_epoch=now_epoch - 10.0,
        candle_ts_epoch=None,
        market_open=True,
        require_live_quotes=True,
        max_ltp_age_sec=2.5,
        max_candle_age_sec=120.0,
        now_epoch=now_epoch,
    )

    assert verdict["ok"] is False
    assert "LTP_STALE" in verdict["reasons"]
