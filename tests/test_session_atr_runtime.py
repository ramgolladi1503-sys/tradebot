from __future__ import annotations

import socket
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.market_data import calculate_session_atr_state as runtime_calculate_session_atr_state
from core.orchestrator import _strategy_context_snapshot_metadata
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from core.session_atr import calculate_session_atr_state
from core.session_bar_history import CompletedBarSnapshot, SessionBarHistoryState


IST = ZoneInfo("Asia/Kolkata")


def _build_bar(index: int, *, start: datetime, base: float) -> CompletedBarSnapshot:
    bar_start = start + timedelta(minutes=index)
    bar_end = bar_start + timedelta(minutes=1)
    open_price = base + index
    return CompletedBarSnapshot(
        symbol="NIFTY",
        session_date="2026-07-15",
        timeframe="1m",
        bar_start_timestamp=bar_start.isoformat(),
        bar_end_timestamp=bar_end.isoformat(),
        open=open_price,
        high=open_price + 2.0,
        low=open_price - 1.0,
        close=open_price + 1.0,
        volume=1000,
        source="unit_test",
        source_timestamp=bar_end.isoformat(),
        receipt_timestamp=(bar_end + timedelta(seconds=1)).isoformat(),
        is_complete=True,
    )


def _build_state(bar_count: int = 35) -> SessionBarHistoryState:
    start = datetime(2026, 7, 15, 9, 15, tzinfo=IST)
    bars = [_build_bar(index, start=start, base=100.0) for index in range(bar_count)]
    return SessionBarHistoryState(
        symbol="NIFTY",
        session_date="2026-07-15",
        timeframe="1m",
        source="unit_test",
        partial_session=False,
        is_complete=True,
        history_bound="session",
        completed_bar_count=len(bars),
        latest_completed_timestamp=bars[-1].bar_end_timestamp if bars else None,
        open_price=100.0,
        day_high=200.0,
        day_low=99.0,
        previous_completed_close=bars[-2].close if len(bars) > 1 else None,
        history_hash="history-hash",
        completed_bar_history=bars,
    )


def test_session_atr_calculator_emits_truthful_short_and_long_values() -> None:
    state = _build_state(35)

    result = calculate_session_atr_state(state)

    assert result.contract_version == "atr_short_long_v1"
    assert result.short_lookback == 5
    assert result.long_lookback == 30
    assert result.atr_short == pytest.approx(3.0)
    assert result.atr_long == pytest.approx(3.0)
    assert result.short_available is True
    assert result.long_available is True
    assert result.short_status == "AVAILABLE"
    assert result.long_status == "AVAILABLE"
    assert result.continuity_status == "AVAILABLE"
    assert result.source_history_hash == "history-hash"


def test_session_atr_gap_resets_contiguity_and_prevents_cross_gap_contamination() -> None:
    start = datetime(2026, 7, 15, 9, 15, tzinfo=IST)
    bars = [
        _build_bar(index, start=start, base=1000.0)
        for index in range(10)
    ]
    post_gap_start = start + timedelta(minutes=20)
    bars.extend(
        [
            CompletedBarSnapshot(
                symbol="NIFTY",
                session_date="2026-07-15",
                timeframe="1m",
                bar_start_timestamp=(post_gap_start + timedelta(minutes=index)).isoformat(),
                bar_end_timestamp=(post_gap_start + timedelta(minutes=index + 1)).isoformat(),
                open=110.0 + index,
                high=112.0 + index,
                low=109.0 + index,
                close=111.0 + index,
                volume=1000,
                source="unit_test",
                source_timestamp=(post_gap_start + timedelta(minutes=index + 1)).isoformat(),
                receipt_timestamp=(post_gap_start + timedelta(minutes=index + 1, seconds=1)).isoformat(),
                is_complete=True,
            )
            for index in range(5)
        ]
    )
    state = SessionBarHistoryState(
        symbol="NIFTY",
        session_date="2026-07-15",
        timeframe="1m",
        source="unit_test",
        partial_session=False,
        is_complete=True,
        history_bound="session",
        completed_bar_count=len(bars),
        latest_completed_timestamp=bars[-1].bar_end_timestamp,
        open_price=1000.0,
        day_high=1200.0,
        day_low=99.0,
        previous_completed_close=999.0,
        history_hash="gap-hash",
        completed_bar_history=bars,
    )

    result = calculate_session_atr_state(state)

    assert result.gap_count == 1
    assert result.current_contiguous_bar_count == 5
    assert result.atr_short == pytest.approx(3.0)
    assert result.atr_long is None
    assert result.short_status == "AVAILABLE"
    assert result.long_status == "CONTIGUITY_REWARMING"
    assert result.continuity_status == "CONTIGUITY_REWARMING"


def test_runtime_metadata_and_context_receive_the_calculated_atr_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _build_state(35)
    session_atr_state = calculate_session_atr_state(state)

    runtime_payload = {
        "symbol": "NIFTY",
        "spot": 135.0,
        "ltp": 135.0,
        "open_price": state.open_price,
        "day_high": state.day_high,
        "day_low": state.day_low,
        "previous_completed_close": state.previous_completed_close,
        "completed_bar_history": state.history_payload(),
        "completed_bar_history_provenance": state.provenance_payload(
            source_component="tests.test_session_atr_runtime",
            receipt_timestamp="2026-07-15T09:50:01+05:30",
        ),
        "atr_short": session_atr_state.atr_short,
        "atr_long": session_atr_state.atr_long,
        "atr_short_status": session_atr_state.short_status,
        "atr_long_status": session_atr_state.long_status,
        "atr_short_long_state": session_atr_state.to_dict(),
        "atr_short_long_provenance": session_atr_state.provenance_payload(
            source_component="core.session_atr.calculate_session_atr_state",
            receipt_timestamp="2026-07-15T09:50:01+05:30",
        ),
        "metadata": {},
        "timestamp_ist": "2026-07-15T09:50:00+05:30",
        "ltp_ts_epoch": 1721028000.0,
        "market_open": True,
    }
    metadata = _strategy_context_snapshot_metadata(runtime_payload)
    runtime_payload["metadata"] = {
        **metadata,
        "atr_short_long_state": session_atr_state.to_dict(),
        "atr_short_long_provenance": {
            "source_component": "core.session_atr.calculate_session_atr_state",
            "source_history_hash": session_atr_state.source_history_hash,
            "calculation_hash": session_atr_state.calculation_hash,
        },
    }

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network not allowed")),
    )
    monkeypatch.setattr(
        threading.Thread,
        "start",
        lambda self: (_ for _ in ()).throw(AssertionError("threads not allowed")),
    )

    ctx = _strategy_context_from_market_symbol("NIFTY", runtime_payload)

    assert runtime_calculate_session_atr_state is calculate_session_atr_state
    assert metadata["strategy_context_truth"]["atr_short"] == pytest.approx(3.0)
    assert metadata["strategy_context_truth"]["atr_long"] == pytest.approx(3.0)
    assert metadata["strategy_context_provenance"]["atr_short"]["source_component"] == "core.session_atr.calculate_session_atr_state"
    assert metadata["strategy_context_provenance"]["atr_short"]["lookback"] == "5"
    assert metadata["strategy_context_provenance"]["atr_long"]["lookback"] == "30"
    assert ctx.atr_short == pytest.approx(3.0)
    assert ctx.atr_long == pytest.approx(3.0)
    assert ctx.metadata["atr_short_long_state"]["contract_version"] == "atr_short_long_v1"
    assert ctx.metadata["atr_short_long_state"]["atr_short"] == pytest.approx(3.0)
    assert ctx.metadata["atr_short_long_provenance"]["source_component"] == "core.session_atr.calculate_session_atr_state"
