from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from aixion_trade_intelligence.cas_a1_finalization_replay import (
    CasA1FinalizationReplayError,
    analyze_finalization_replay,
)


IST = ZoneInfo("Asia/Kolkata")


def _row(clock: str, key: str, ltp: float, bid=None, ask=None):
    return {
        "ts": datetime.fromisoformat(f"2026-08-03T{clock}+05:30"),
        "instrument_key": key,
        "ltp": ltp,
        "bid_price": bid,
        "ask_price": ask,
    }


def _fixture(final_time="15:29:02"):
    idx = "NSE_INDEX|Nifty 50"
    fut = "NSE_FO|NIFTY_FUT"
    ce = "NSE_FO|65871"
    pe = "NSE_FO|65872"
    return [
        _row("14:45:01", idx, 24590.0),
        _row("15:10:00", idx, 24578.0),
        _row("15:14:59", idx, 24575.1),
        _row("15:27:10", idx, 24573.35),
        _row("15:28:50", idx, 24573.35),
        _row(final_time, idx, 24774.30),
        _row("15:29:15", idx, 24774.30),
        _row("15:29:03", fut, 24760.0),
        _row("15:39:02", fut, 24770.0),
        _row("15:29:02.500000", ce, 40.0, 39.9, 40.0),
        _row("15:29:02.600000", pe, 60.0, 59.9, 60.0),
    ]


def test_detects_largest_finalization_discontinuity_without_upgrading_semantics():
    result = analyze_finalization_replay(
        _fixture(),
        session_date="2026-08-03",
        futures_instrument_key="NSE_FO|NIFTY_FUT",
        ce_instrument_key="NSE_FO|65871",
        pe_instrument_key="NSE_FO|65872",
    )
    assert result.pre_jump_ltp == pytest.approx(24573.35)
    assert result.jump_ltp == pytest.approx(24774.30)
    assert result.jump_points == pytest.approx(200.95)
    assert result.candidate_semantics == "REPLAY_PROXY_FROM_INDEX_DISCONTINUITY"
    assert result.official_final_cas_semantics_verified is False
    assert result.target_start_causal is True
    assert result.ce_first_ask_after_candidate == pytest.approx(40.0)
    assert result.pe_first_ask_after_candidate == pytest.approx(60.0)
    assert result.broker_write_authority is False
    assert result.order_authority is False
    assert result.prospective_supported is False
    assert result.execution_viable is False


def test_same_minute_future_tick_before_index_proxy_is_not_causal():
    rows = _fixture(final_time="15:29:10")
    result = analyze_finalization_replay(
        rows,
        session_date="2026-08-03",
        futures_instrument_key="NSE_FO|NIFTY_FUT",
    )
    assert result.target_start_causal is False
    assert result.official_final_cas_semantics_verified is False


def test_missing_finalization_window_fails_closed():
    rows = [row for row in _fixture() if row["instrument_key"] != "NSE_INDEX|Nifty 50" or row["ts"].hour < 15]
    with pytest.raises(CasA1FinalizationReplayError, match="insufficient exact index ticks"):
        analyze_finalization_replay(rows, session_date="2026-08-03")


def test_wrong_index_identity_fails_closed():
    with pytest.raises(CasA1FinalizationReplayError, match="insufficient exact index ticks"):
        analyze_finalization_replay(
            _fixture(),
            session_date="2026-08-03",
            index_instrument_key="NSE_INDEX|WRONG",
        )


def test_replay_proxy_never_claims_prospective_or_execution_support():
    result = analyze_finalization_replay(_fixture(), session_date="2026-08-03")
    assert result.official_final_cas_semantics_verified is False
    assert result.prospective_supported is False
    assert result.execution_viable is False
    assert result.structural_edge_certified is False
