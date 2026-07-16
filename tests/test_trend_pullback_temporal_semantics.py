from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.option_pressure import generate_option_pressure_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates
from tests.test_opening_range_retest_temporal_fixture_contract import (
    CALL_VALID_ROWS,
    OPENING_RANGE_ROWS,
    _history_state_for_rows,
)


IST = ZoneInfo("Asia/Kolkata")


def _bars(
    closes: tuple[float, ...],
    *,
    session_date: str = "2026-07-14",
) -> list[dict[str, object]]:
    start = datetime.fromisoformat(f"{session_date}T09:15:00+05:30")
    bars: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        bar_start = start + timedelta(minutes=index)
        bar_end = bar_start + timedelta(minutes=1)
        bars.append(
            {
                "symbol": "NIFTY",
                "session_date": session_date,
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


def test_ready_untriggered_setup_expires_before_late_trigger():
    stale_history = _bars((22590.0, 22630.0, 22615.0, 22580.0, 22638.0))
    stale = generate_trend_pullback_candidates(_context(completed_bar_history=stale_history), _regime(up=0.72))
    assert stale == ()

    fresh = generate_trend_pullback_candidates(
        _context(completed_bar_history=_bars((22590.0, 22630.0, 22615.0, 22635.0))),
        _regime(up=0.72),
    )
    assert len(fresh) == 1
    assert fresh[0].evidence["setup_identity"]["expiry_timestamp"] == "2026-07-14T09:19:00+05:30"


def test_session_b_does_not_inherit_session_a_ready_setup():
    session_a = generate_trend_pullback_candidates(
        _context(
            completed_bar_history=_bars((22590.0, 22630.0, 22615.0), session_date="2026-07-14"),
        ),
        _regime(up=0.72),
    )
    assert session_a == ()

    session_b = generate_trend_pullback_candidates(
        _context(
            completed_bar_history=_bars((22635.0,), session_date="2026-07-15"),
        ),
        _regime(up=0.72),
    )
    assert session_b == ()


def test_complete_new_session_b_setup_can_emit():
    session_b = generate_trend_pullback_candidates(
        _context(
            completed_bar_history=_bars((22590.0, 22630.0, 22615.0, 22635.0), session_date="2026-07-15"),
        ),
        _regime(up=0.72),
    )
    assert len(session_b) == 1
    identity = session_b[0].evidence["setup_identity"]
    assert identity["session_date"] == "2026-07-15"
    assert identity["expiry_timestamp"] == "2026-07-15T09:19:00+05:30"


def test_future_mutation_cannot_change_earlier_trend_pullback_checkpoint():
    base_history = _bars((22590.0, 22630.0, 22615.0, 22635.0, 22620.0, 22640.0))
    mutated_history = _bars((22590.0, 22630.0, 22615.0, 22635.0, 22300.0, 22850.0))

    base = generate_trend_pullback_candidates(
        _context(completed_bar_history=base_history[:4]),
        _regime(up=0.72),
    )
    mutated = generate_trend_pullback_candidates(
        _context(completed_bar_history=mutated_history[:4]),
        _regime(up=0.72),
    )

    assert len(base) == 1
    assert len(mutated) == 1
    assert base[0].strategy_id == mutated[0].strategy_id
    assert base[0].direction == mutated[0].direction
    assert round(base[0].raw_score, 6) == round(mutated[0].raw_score, 6)
    assert base[0].evidence["setup_identity"] == mutated[0].evidence["setup_identity"]

    later_base = generate_trend_pullback_candidates(_context(completed_bar_history=base_history), _regime(up=0.72))
    later_mutated = generate_trend_pullback_candidates(
        _context(completed_bar_history=mutated_history),
        _regime(up=0.72),
    )

    assert len(later_base) == 1
    assert later_base[0].strategy_id == "trend_pullback_v1"
    assert later_base[0].direction == "BUY_CALL"
    assert round(later_base[0].raw_score, 6) == 0.612584
    assert later_base[0].status == "RAW_CANDIDATE"
    assert later_base[0].evidence["setup_identity"]["expiry_timestamp"] == "2026-07-14T09:21:00+05:30"
    assert later_mutated == ()


def test_opening_range_retest_control_unchanged_by_trend_pullback_temporal_repair():
    state = _history_state_for_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    candidates = generate_opening_range_retest_candidates(
        _context(
            orb_high=max(bar[2] for bar in OPENING_RANGE_ROWS),
            orb_low=min(bar[3] for bar in OPENING_RANGE_ROWS),
            pe_premium_change=0.0,
            completed_bar_history=state.history_payload(),
        ),
        _regime(),
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.strategy_id == "opening_range_retest_v1"
    assert candidate.direction == "BUY_CALL"
    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.raw_score == pytest.approx(0.36150442477876105, rel=0.0, abs=1e-6)
    assert candidate.entry_trigger == "opening_range_breakout_retest_hold"
    assert candidate.invalid_if == "price_returns_inside_opening_range"
    assert candidate.rank_reason == "opening range breakout retest held"


def test_option_pressure_confirmation_control_unchanged_by_trend_pullback_temporal_repair():
    assert generate_option_pressure_candidates(_context(), _regime()) == ()


@pytest.mark.parametrize(
    ("history_factory", "expected_message"),
    [
        pytest.param(
            lambda: _mutated_history_with_session_mismatch(),
            "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=- invalid_fields=completed_bar_history[0].session_date,completed_bar_history[1].session_date,completed_bar_history[2].session_date,completed_bar_history[3].session_date reason=invalid_completed_history",
            id="mixed-session",
        ),
        pytest.param(
            lambda: _mutated_history_with_unordered_timestamps(),
            "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=- invalid_fields=completed_bar_history[3].bar_start_timestamp reason=invalid_completed_history",
            id="unordered-timestamps",
        ),
        pytest.param(
            lambda: _mutated_history_with_duplicate_timestamps(),
            "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=- invalid_fields=completed_bar_history[3].bar_start_timestamp reason=invalid_completed_history",
            id="duplicate-timestamps",
        ),
        pytest.param(
            lambda: _mutated_history_with_non_1m_interval(),
            "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=- invalid_fields=completed_bar_history[2].timeframe reason=invalid_completed_history",
            id="non-1m-interval",
        ),
        pytest.param(
            lambda: _mutated_history_with_missing_close(),
            "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=- invalid_fields=completed_bar_history[2].close reason=invalid_completed_history",
            id="missing-close",
        ),
        pytest.param(
            lambda: _bars((22590.0, 22630.0, 22615.0)),
            "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=completed_bar_history invalid_fields=- reason=missing_required_temporal_evidence",
            id="insufficient-history",
        ),
    ],
)
def test_malformed_completed_history_blocks_trend_pullback(
    history_factory,
    expected_message: str,
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level(logging.WARNING):
        result = generate_trend_pullback_candidates(
            _context(completed_bar_history=history_factory()),
            _regime(up=0.72),
        )

    assert result == ()
    assert [record.message for record in caplog.records if "event=STRATEGY_EVIDENCE_BLOCKED" in record.message] == [
        expected_message
    ]


def _mutated_history_with_session_mismatch() -> list[dict[str, object]]:
    history = _bars((22590.0, 22630.0, 22615.0, 22635.0))
    for bar in history:
        bar["session_date"] = "2026-07-14"
    history[-1]["session_date"] = "2026-07-15"
    return history


def _mutated_history_with_unordered_timestamps() -> list[dict[str, object]]:
    history = _bars((22590.0, 22630.0, 22615.0, 22635.0))
    history[2]["bar_start_timestamp"] = "2026-07-14T09:20:00+05:30"
    history[2]["bar_end_timestamp"] = "2026-07-14T09:21:00+05:30"
    history[3]["bar_start_timestamp"] = "2026-07-14T09:19:00+05:30"
    history[3]["bar_end_timestamp"] = "2026-07-14T09:20:00+05:30"
    return history


def _mutated_history_with_duplicate_timestamps() -> list[dict[str, object]]:
    history = _bars((22590.0, 22630.0, 22615.0, 22635.0))
    history[3]["bar_start_timestamp"] = history[2]["bar_start_timestamp"]
    history[3]["bar_end_timestamp"] = history[2]["bar_end_timestamp"]
    return history


def _mutated_history_with_non_1m_interval() -> list[dict[str, object]]:
    history = _bars((22590.0, 22630.0, 22615.0, 22635.0))
    history[2]["timeframe"] = "5m"
    return history


def _mutated_history_with_missing_close() -> list[dict[str, object]]:
    history = _bars((22590.0, 22630.0, 22615.0, 22635.0))
    history[2]["close"] = None
    return history


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
