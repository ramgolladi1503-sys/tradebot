from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.trend_pullback import generate_trend_pullback_candidates


IST = ZoneInfo("Asia/Kolkata")


def _bars(closes: tuple[float, ...]) -> list[dict[str, object]]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    bars: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        bar_start = start + timedelta(minutes=index)
        bar_end = bar_start + timedelta(minutes=1)
        bars.append(
            {
                "symbol": "NIFTY",
                "session_date": "2026-07-14",
                "timeframe": "1m",
                "bar_start_timestamp": bar_start.isoformat(),
                "bar_end_timestamp": bar_end.isoformat(),
                "open": close - 5.0,
                "high": close + 10.0,
                "low": close - 10.0,
                "close": close,
                "volume": 1000.0 + (index * 100.0),
                "source": "unit_test",
                "source_timestamp": bar_end.isoformat(),
                "receipt_timestamp": (bar_end + timedelta(seconds=1)).isoformat(),
                "is_complete": True,
            }
        )
    return bars


def _regime(*, up: float = 0.0, down: float = 0.0) -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP" if up >= down else "TREND_DOWN",
        scores={
            "TREND_UP": up,
            "TREND_DOWN": down,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.0,
            "VOLATILITY_EXPANSION": 0.0,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
    )


def _context(**overrides: object) -> StrategyContext:
    payload = {
        "symbol": "NIFTY",
        "ts_epoch": 1721028600.0,
        "spot_ltp": 22620.0,
        "open_price": 22500.0,
        "vwap": 22540.0,
        "day_high": 22620.0,
        "day_low": 22460.0,
        "nearest_support": 22590.0,
        "nearest_resistance": 22600.0,
        "range_width_pct": 0.14,
        "atr": 70.0,
        "volume_z": 1.5,
        "vwap_slope": 0.03,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 12.0,
        "pe_premium_change": 12.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 35,
        "minutes_to_close": 280,
        "completed_bar_history": _bars((22590.0, 22630.0, 22615.0, 22635.0)),
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def test_missing_completed_history_blocks_trend_pullback():
    assert generate_trend_pullback_candidates(
        _context(completed_bar_history=None),
        _regime(up=0.72),
    ) == ()


def test_bullish_two_bar_vwap_cross_without_trend_does_not_emit():
    assert generate_trend_pullback_candidates(
        _context(
            completed_bar_history=_bars((22590.0, 22620.0)),
        ),
        _regime(up=0.72),
    ) == ()


def test_bearish_two_bar_vwap_cross_without_trend_does_not_emit():
    assert generate_trend_pullback_candidates(
        _context(
            spot_ltp=22520.0,
            vwap=22540.0,
            nearest_support=22510.0,
            nearest_resistance=22600.0,
            completed_bar_history=_bars((22620.0, 22590.0)),
        ),
        _regime(down=0.72),
    ) == ()


def test_valid_bullish_trend_pullback_trigger_emits_once():
    candidates = generate_trend_pullback_candidates(_context(), _regime(up=0.72))
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "trend_pullback_v1"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.raw_score > 0.6
    assert candidate.evidence["temporal_contract_version"] == "trend_pullback_temporal_v1"
    assert candidate.evidence["setup_identity"]["direction"] == "BUY_CALL"
    assert candidate.evidence["setup_identity"]["expiry_timestamp"] == "2026-07-14T09:19:00+05:30"

    later_candles = generate_trend_pullback_candidates(
        _context(completed_bar_history=_bars((22590.0, 22630.0, 22615.0, 22635.0, 22638.0))),
        _regime(up=0.72),
    )
    assert later_candles == ()


def test_valid_bullish_history_anchor_break_invalidates_setup(caplog):
    caplog.set_level(logging.WARNING)
    candidates = generate_trend_pullback_candidates(
        _context(
            completed_bar_history=_bars((22570.0, 22590.0, 22630.0, 22580.0, 22625.0)),
        ),
        _regime(up=0.72),
    )
    assert candidates == ()
    assert any("runtime_strategy_id=trend_pullback_v1" in record.message for record in caplog.records)
    assert any("reason=pullback_breaks_anchor" in record.message for record in caplog.records)


def test_valid_bearish_trend_pullback_trigger_emits_once():
    candidates = generate_trend_pullback_candidates(
        _context(
            spot_ltp=22520.0,
            vwap=22540.0,
            nearest_support=22510.0,
            nearest_resistance=22580.0,
            pe_premium_change=13.0,
            ce_premium_change=0.0,
            completed_bar_history=_bars((22620.0, 22530.0, 22550.0, 22520.0)),
        ),
        _regime(down=0.72),
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "trend_pullback_v1"
    assert candidate.direction == "BUY_PUT"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.evidence["temporal_contract_version"] == "trend_pullback_temporal_v1"
    assert candidate.evidence["setup_identity"]["expiry_timestamp"] == "2026-07-14T09:19:00+05:30"

    later_candles = generate_trend_pullback_candidates(
        _context(
            spot_ltp=22520.0,
            vwap=22540.0,
            nearest_support=22510.0,
            nearest_resistance=22580.0,
            pe_premium_change=13.0,
            ce_premium_change=0.0,
            completed_bar_history=_bars((22600.0, 22520.0, 22535.0, 22535.0)),
        ),
        _regime(down=0.72),
    )
    assert later_candles == ()


def test_valid_bearish_history_anchor_break_invalidates_setup(caplog):
    caplog.set_level(logging.WARNING)
    candidates = generate_trend_pullback_candidates(
        _context(
            spot_ltp=22520.0,
            vwap=22540.0,
            nearest_support=22510.0,
            nearest_resistance=22580.0,
            pe_premium_change=13.0,
            ce_premium_change=0.0,
            completed_bar_history=_bars((22650.0, 22630.0, 22530.0, 22610.0, 22570.0)),
        ),
        _regime(down=0.72),
    )
    assert candidates == ()
    assert any("runtime_strategy_id=trend_pullback_v1" in record.message for record in caplog.records)
    assert any("reason=pullback_breaks_anchor" in record.message for record in caplog.records)


def test_invalidated_setup_cannot_revive_on_later_trigger():
    candidates = generate_trend_pullback_candidates(
        _context(
            completed_bar_history=_bars((22570.0, 22590.0, 22630.0, 22580.0, 22625.0, 22628.0)),
        ),
        _regime(up=0.72),
    )
    assert candidates == ()


def test_new_setup_after_invalidation_can_emit_with_new_identity():
    initial = generate_trend_pullback_candidates(_context(), _regime(up=0.72))
    assert len(initial) == 1
    initial_identity = initial[0].evidence["setup_identity"]

    fresh_history = _bars((22570.0, 22590.0, 22630.0, 22580.0, 22625.0, 22595.0, 22632.0, 22608.0, 22636.0))
    later = generate_trend_pullback_candidates(
        _context(completed_bar_history=fresh_history),
        _regime(up=0.72),
    )
    assert len(later) == 1
    later_identity = later[0].evidence["setup_identity"]
    assert later_identity["direction"] == "BUY_CALL"
    assert later_identity["expiry_timestamp"] == "2026-07-14T09:24:00+05:30"
    assert later_identity != initial_identity
