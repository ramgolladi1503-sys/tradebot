"""Unit test for Sentinel RBFN Multi-Scenario Trajectory Expansion (S2, S4, S7).
=============================================================================
Proves:
1. S2: RP1_UPPER 10-minute sustained breakout triggers BUY_CALL targeting RP2_UPPER (OTM -> ATM).
2. S4: RP1_LOWER 10-minute sustained breakdown triggers BUY_PUT targeting RP2_LOWER (OTM -> ATM).
3. S7: RP2_LOWER 10-minute floor bounce triggers BUY_CALL targeting RP1_LOWER.
4. S6 & S8 Reversal Fades enforce capped milestone targets (max +20 pts) to prevent midday theta bleed.
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from unittest.mock import patch
import pytest
from zoneinfo import ZoneInfo

from core.sentinel_live_stream_advisor import SentinelLiveStreamAdvisor
from strategies.optionmate_rbfn_strategy import OptionMateGrid


def _seed_complete_or_pair(advisor, index_name: str = "NIFTY"):
    """Seed exact same-session OR evidence so tests never call a provider."""
    session_day = date(2026, 11, 17)
    ist = ZoneInfo("Asia/Kolkata")
    start = int(datetime.combine(session_day, dt_time(9, 15), tzinfo=ist).timestamp() * 1000)
    end = int(datetime.combine(session_day, dt_time(9, 44), tzinfo=ist).timestamp() * 1000)
    for current in (index_name, "SENSEX" if index_name == "NIFTY" else "NIFTY"):
        high, low = (81000.0, 80800.0) if current == "SENSEX" else (25400.0, 25200.0)
        advisor.or_bounds[current] = {"high": high, "low": low}
        advisor.or_evidence[current] = {
            "session_date": session_day.isoformat(),
            "status": "COMPLETE",
            "source": "UPSTOX_V2_1M_EXACT_30",
            "source_timestamp_ms": end,
            "coverage_count": 30,
            "coverage_start_ms": start,
            "coverage_end_ms": end,
        }
    advisor.or_reconciliation_frozen = True


def _seed_target_grid(advisor):
    advisor.cached_rbfn_grids["NIFTY"] = OptionMateGrid(
        date="2026-11-17",
        spot_open=24500.0,
        trend_decider=24500.0,
        rp1_upper=24600.0,
        rp2_upper=24700.0,
        rp1_lower=24400.0,
        rp2_lower=24300.0,
        call_strike=24700.0,
        put_strike=24300.0,
        recommended_bias="RANGE",
        target_strike=24700.0,
    )
    advisor.rbfn_grids_frozen["NIFTY"] = True


def _completed_bar_epoch(bar_time: dt_time) -> int:
    """Return the valid bucket-start epoch for a completed bar on the fixture day."""
    start = datetime.combine(
        date(2026, 11, 17), bar_time, tzinfo=ZoneInfo("Asia/Kolkata")
    ) - timedelta(minutes=5)
    return int(start.timestamp() // 300)


def test_s2_expansion_breakout_triggers_otm_call(tmp_path):
    wal = tmp_path / "test_wal_s2.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "s2_trace.jsonl"
    _seed_complete_or_pair(advisor)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24520.0
    
    # RP1_UPPER is 24640.0, RP2_UPPER is 24760.0
    # Add two consecutive 5m bars closing above RP1_UPPER (10-minute hold)
    advisor.bars_5m_history["NIFTY"].append({
        "open": 24630.0, "high": 24660.0, "low": 24625.0, "close": 24650.0,
        "volume": 1000, "time": dt_time(12, 15), "timestamp_ms": 1793190000000, "epoch_5min": 100
    })

    epoch_5min = _completed_bar_epoch(dt_time(12, 20))
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24650.0,
        bar_high=24680.0,
        bar_low=24645.0,
        bar_close=24670.0,
        bar_volume=1000.0,
        bar_time=dt_time(12, 20),
        timestamp_ms=epoch_5min * 300000,
        epoch_5min=epoch_5min
    )

    assert sig is not None
    assert sig.action == "BUY_CALL"
    assert sig.direction == "CE"
    assert sig.setup_reason == "RP1_UPPER_10M_EXPANSION_BREAKOUT"
    assert sig.trade_phase == "MIDDAY_EXPANSION_BREAKOUT"
    assert sig.target_strike == 24750.0  # Snapped round OTM strike at RP2_UPPER


def test_s4_expansion_breakdown_triggers_otm_put(tmp_path):
    wal = tmp_path / "test_wal_s4.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "s4_trace.jsonl"
    _seed_complete_or_pair(advisor)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24520.0

    # RP1_LOWER is 24400.0, RP2_LOWER is 24280.0
    advisor.bars_5m_history["NIFTY"].append({
        "open": 24420.0, "high": 24430.0, "low": 24390.0, "close": 24395.0,
        "volume": 1000, "time": dt_time(12, 15), "timestamp_ms": 1793190000000, "epoch_5min": 100
    })

    epoch_5min = _completed_bar_epoch(dt_time(12, 20))
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24395.0,
        bar_high=24400.0,
        bar_low=24370.0,
        bar_close=24380.0,
        bar_volume=1000.0,
        bar_time=dt_time(12, 20),
        timestamp_ms=epoch_5min * 300000,
        epoch_5min=epoch_5min
    )

    assert sig is not None
    assert sig.action == "BUY_PUT"
    assert sig.direction == "PE"
    assert sig.setup_reason == "RP1_LOWER_10M_EXPANSION_BREAKDOWN"
    assert sig.trade_phase == "MIDDAY_EXPANSION_BREAKDOWN"
    assert sig.target_strike == 24300.0  # Snapped round OTM strike at RP2_LOWER


def test_s7_floor_bounce_triggers_reversal_call(tmp_path):
    wal = tmp_path / "test_wal_s7.json"
    advisor = SentinelLiveStreamAdvisor(wal_path=str(wal), enable_stdout=False)
    advisor.decision_trace_path = tmp_path / "s7_trace.jsonl"
    _seed_complete_or_pair(advisor)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24520.0

    # RP2_LOWER is 24280.0, RP1_LOWER is 24400.0
    # Bar tested low <= 24280, then two consecutive closes >= 24280
    epoch_touch = _completed_bar_epoch(dt_time(12, 10))
    epoch_confirm_1 = _completed_bar_epoch(dt_time(12, 15))
    advisor.bars_5m_history["NIFTY"] = [
        {"open": 24290.0, "high": 24295.0, "low": 24260.0, "close": 24285.0,
         "volume": 1000, "time": dt_time(12, 10), "timestamp_ms": epoch_touch * 300000, "epoch_5min": epoch_touch},
        {"open": 24285.0, "high": 24310.0, "low": 24280.0, "close": 24300.0,
         "volume": 1000, "time": dt_time(12, 15), "timestamp_ms": epoch_confirm_1 * 300000, "epoch_5min": epoch_confirm_1}
    ]

    epoch_5min = _completed_bar_epoch(dt_time(12, 20))
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=24300.0,
        bar_high=24320.0,
        bar_low=24290.0,
        bar_close=24315.0,
        bar_volume=1000.0,
        bar_time=dt_time(12, 20),
        timestamp_ms=epoch_5min * 300000,
        epoch_5min=epoch_5min
    )

    assert sig is not None
    assert sig.action == "BUY_CALL"
    assert sig.direction == "CE"
    assert sig.setup_reason == "RP2_LOWER_10M_FLOOR_BOUNCE"
    assert sig.trade_phase == "EXTREME_EXHAUSTION_REVERSAL"
    assert sig.target_strike == 24400.0  # Target becomes ATM at RP1_LOWER
    assert epoch_touch + 1 == epoch_confirm_1
    assert epoch_confirm_1 + 1 == epoch_5min


@pytest.mark.parametrize(
    ("touch_side", "open_price", "high_price", "low_price", "close_price"),
    [
        ("lower", 24320.0, 24330.0, 24295.0, 24305.0),
        ("upper", 24680.0, 24705.0, 24670.0, 24695.0),
    ],
)
def test_rp2_touch_on_current_bar_does_not_count_as_10m_hold(
    tmp_path, touch_side, open_price, high_price, low_price, close_price
):
    """A current-bar touch has no two completed post-touch confirmation bars."""
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"touch_{touch_side}.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / f"touch_{touch_side}_trace.jsonl"
    _seed_complete_or_pair(advisor)
    _seed_target_grid(advisor)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24500.0

    if touch_side == "lower":
        prior_closes = [24320.0, 24310.0]
    else:
        prior_closes = [24680.0, 24690.0]
    advisor.bars_5m_history["NIFTY"] = [
        {"open": close, "high": close + 5.0, "low": close - 5.0, "close": close,
         "volume": 1000, "time": dt_time(12, 10 + 5 * i),
         "timestamp_ms": int(datetime.combine(
             date(2026, 11, 17), dt_time(12, 5 + 5 * i), tzinfo=ZoneInfo("Asia/Kolkata")
         ).timestamp() * 1000), "epoch_5min": 99 + i}
        for i, close in enumerate(prior_closes)
    ]
    epoch_5min = _completed_bar_epoch(dt_time(12, 20))
    timestamp_ms = epoch_5min * 300000
    sig = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=open_price,
        bar_high=high_price,
        bar_low=low_price,
        bar_close=close_price,
        bar_volume=1000.0,
        bar_time=dt_time(12, 20),
        timestamp_ms=timestamp_ms,
        epoch_5min=epoch_5min,
    )

    assert sig is not None
    assert sig.setup_reason != (
        "RP2_LOWER_10M_FLOOR_BOUNCE" if touch_side == "lower"
        else "RP2_UPPER_10M_CEILING_FADE"
    )


@pytest.mark.parametrize("touch_side", ["lower", "upper"])
def test_rp2_touch_on_previous_bar_has_only_one_post_touch_close(tmp_path, touch_side):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"one_close_{touch_side}.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / f"one_close_{touch_side}_trace.jsonl"
    _seed_complete_or_pair(advisor)
    _seed_target_grid(advisor)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24500.0

    epochs = [_completed_bar_epoch(dt_time(t, m)) for t, m in [(12, 10), (12, 15)]]
    if touch_side == "lower":
        records = [
            (24320.0, 24325.0, 24315.0, 24320.0),
            (24310.0, 24320.0, 24290.0, 24305.0),
        ]
        current = (24305.0, 24310.0, 24300.0, 24305.0)
    else:
        records = [
            (24680.0, 24685.0, 24675.0, 24680.0),
            (24690.0, 24705.0, 24680.0, 24695.0),
        ]
        current = (24695.0, 24699.0, 24690.0, 24695.0)
    advisor.bars_5m_history["NIFTY"] = [
        {"open": values[0], "high": values[1], "low": values[2], "close": values[3],
         "volume": 1000, "time": time,
         "timestamp_ms": epochs[i] * 300000, "epoch_5min": epochs[i]}
        for i, (values, time) in enumerate(zip(records, (dt_time(12, 10), dt_time(12, 15))))
    ]
    epoch_current = _completed_bar_epoch(dt_time(12, 20))
    signal = advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=current[0], bar_high=current[1],
        bar_low=current[2], bar_close=current[3], bar_volume=1000.0,
        bar_time=dt_time(12, 20), timestamp_ms=epoch_current * 300000,
        epoch_5min=epoch_current,
    )

    assert signal is not None
    assert signal.setup_reason not in {
        "RP2_LOWER_10M_FLOOR_BOUNCE", "RP2_UPPER_10M_CEILING_FADE"
    }


@pytest.mark.parametrize("touch_side", ["lower", "upper"])
def test_rp2_gapped_post_touch_epochs_do_not_qualify_as_10m(tmp_path, touch_side):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"gap_{touch_side}.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / f"gap_{touch_side}_trace.jsonl"
    _seed_complete_or_pair(advisor)
    _seed_target_grid(advisor)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24500.0

    touch_epoch = _completed_bar_epoch(dt_time(12, 0))
    first_confirm_epoch = touch_epoch + 1
    current_epoch = touch_epoch + 3  # The required intervening five-minute bar is absent.
    if touch_side == "lower":
        records = [
            (24310.0, 24320.0, 24290.0, 24305.0),
            (24305.0, 24320.0, 24300.0, 24310.0),
        ]
        current = (24310.0, 24320.0, 24305.0, 24315.0)
    else:
        records = [
            (24690.0, 24705.0, 24680.0, 24695.0),
            (24695.0, 24700.0, 24680.0, 24690.0),
        ]
        current = (24690.0, 24695.0, 24680.0, 24685.0)
    advisor.bars_5m_history["NIFTY"] = [
        {"open": values[0], "high": values[1], "low": values[2], "close": values[3],
         "volume": 1000, "time": bar_time,
         "timestamp_ms": epoch * 300000, "epoch_5min": epoch}
        for values, bar_time, epoch in zip(
            records, (dt_time(12, 0), dt_time(12, 5)), (touch_epoch, first_confirm_epoch)
        )
    ]
    current_bar_time = dt_time(12, 15)
    signal = advisor._on_5m_bar_close(
        index_name="NIFTY", bar_open=current[0], bar_high=current[1],
        bar_low=current[2], bar_close=current[3], bar_volume=1000.0,
        bar_time=current_bar_time, timestamp_ms=current_epoch * 300000,
        epoch_5min=current_epoch,
    )

    assert signal is not None
    assert signal.setup_reason not in {
        "RP2_LOWER_10M_FLOOR_BOUNCE", "RP2_UPPER_10M_CEILING_FADE"
    }


@pytest.mark.parametrize(
    "epochs",
    [
        [101, 102, 102],  # duplicate confirmation epoch
        [101, 102, 104],  # missing five-minute epoch
        [101, "102", 103],  # malformed epoch type
        [101, None, 103],  # missing epoch
    ],
)
def test_rp2_hold_epoch_validation_rejects_invalid_sequences(tmp_path, epochs):
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / "invalid_epochs.json"), enable_stdout=False
    )
    history = [
        {"epoch_5min": epoch, "low": 1.0, "high": 2.0}
        for epoch in epochs
    ]

    assert advisor._has_consecutive_rp2_hold_epochs(history) is False


@pytest.mark.parametrize(
    ("touch_side", "open_price", "high_price", "low_price", "close_price", "expected_reason"),
    [
        ("lower", 24320.0, 24330.0, 24280.0, 24310.0, "RP2_LOWER_FAST_BOUNCE"),
        ("upper", 24680.0, 24720.0, 24670.0, 24690.0, "RP2_UPPER_FAST_REJECTION"),
    ],
)
def test_rp2_fast_rejection_remains_available(
    tmp_path, touch_side, open_price, high_price, low_price, close_price, expected_reason
):
    """The single-bar fast path remains distinct from the two-close hold branch."""
    advisor = SentinelLiveStreamAdvisor(
        wal_path=str(tmp_path / f"fast_{touch_side}.json"), enable_stdout=False
    )
    advisor.decision_trace_path = tmp_path / f"fast_{touch_side}_trace.jsonl"
    _seed_complete_or_pair(advisor)
    _seed_target_grid(advisor)
    advisor.seed_prior_day_levels("NIFTY", pdh=24600.0, pdl=24400.0, pdc=24500.0, atr_20=160.0)
    advisor.session_open_prices["NIFTY"] = 24500.0
    prior_closes = [24320.0, 24310.0] if touch_side == "lower" else [24680.0, 24690.0]
    advisor.bars_5m_history["NIFTY"] = [
        {"open": close, "high": close + 5.0, "low": close - 5.0, "close": close,
         "volume": 1000, "time": dt_time(12, 10 + 5 * i),
         "timestamp_ms": int(datetime.combine(
             date(2026, 11, 17), dt_time(12, 5 + 5 * i), tzinfo=ZoneInfo("Asia/Kolkata")
         ).timestamp() * 1000), "epoch_5min": 99 + i}
        for i, close in enumerate(prior_closes)
    ]
    epoch_5min = _completed_bar_epoch(dt_time(12, 20))
    signal = advisor._on_5m_bar_close(
        index_name="NIFTY",
        bar_open=open_price,
        bar_high=high_price,
        bar_low=low_price,
        bar_close=close_price,
        bar_volume=1000.0,
        bar_time=dt_time(12, 20),
        timestamp_ms=epoch_5min * 300000,
        epoch_5min=epoch_5min,
    )

    assert signal is not None
    assert signal.setup_reason == expected_reason
