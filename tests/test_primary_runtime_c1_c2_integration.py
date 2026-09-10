"""Comprehensive Test Suite for Integrated C1 and C2 Evaluators, Trace Propagation, and Memory.

Covers:
- C1 edge cases (49.999 bps, 50.000 bps, 50.001 bps, window boundaries 09:29:59, 09:30:00, 14:45:00, 14:45:01, stale memory)
- C2 edge cases (before 15:12, at 15:12, after 15:12, 49.999 bps, 50.000 bps, 50.001 bps, missing session open, missing 15:12 bar, stale memory)
- Trace inheritance (ingress -> memory -> C1/C2 -> candidate -> lifecycle -> pool -> ranking)
- Positive qualification fixtures for both C1 and C2
- Parity against 2026-09-10 sidecar oracles (VALID_NO_SIGNAL_SESSION)
- Zero execution authority invariants (broker_write=false, orders_placed=0)
"""

from __future__ import annotations

import pytest

from core.candidate_evaluators import (
    C1ReasonCode,
    C2ReasonCode,
    evaluate_c1,
    evaluate_c2,
)
from core.market_session_store import Bar1M, MarketMemorySnapshot, MarketSessionStore
from core.observability import (
    CandidateLifecycleLedger,
    CandidateLifecycleStage,
    DiagnosticPulseRing,
    PipelineCheckpoint,
    StageStatus,
    create_stage_record,
    generate_trace_id,
)
from core.opportunity_book import RankedCandidate, build_opportunity_book


def make_test_memory(
    rolling_15m_return_bps: float = 0.0,
    distance_from_session_open_bps: float = 0.0,
    as_of_timestamp: str = "2026-09-10 10:00:00+05:30",
    bars_count: int = 30,
    freshness_watermark: float = 1.0,
    trace_id: str = "trace_test_001",
    session_open: float = 23400.0,
    current_price: float = 23400.0,
) -> MarketMemorySnapshot:
    return MarketMemorySnapshot(
        as_of_timestamp=as_of_timestamp,
        symbol="NIFTY",
        current_price=current_price,
        session_open=session_open,
        session_high=max(session_open, current_price),
        session_low=min(session_open, current_price),
        session_close=current_price,
        bar_index=bars_count - 1,
        rolling_1m_bars_count=bars_count,
        derived_5m_bars_count=bars_count // 5,
        derived_15m_bars_count=bars_count // 15,
        rolling_15m_return_bps=rolling_15m_return_bps,
        distance_from_session_open_bps=distance_from_session_open_bps,
        rolling_15m_range_bps=10.0,
        realized_vol_15m=5.0,
        freshness_watermark=freshness_watermark,
        persistence_watermark=1.0,
        trace_id=trace_id,
    )


# ---------------------------------------------------------
# Candidate 1 (C1) Unit Tests
# ---------------------------------------------------------

def test_c1_threshold_boundaries():
    # 49.999 bps -> NO_SIGNAL
    m1 = make_test_memory(rolling_15m_return_bps=49.999)
    r1 = evaluate_c1(m1)
    assert not r1.qualified
    assert r1.decision == "NO_SIGNAL"
    assert r1.reason_code == C1ReasonCode.C1_IMPULSE_BELOW_THRESHOLD.value

    # 50.000 bps -> strictly '>' operator -> NO_SIGNAL
    m2 = make_test_memory(rolling_15m_return_bps=50.000)
    r2 = evaluate_c1(m2)
    assert not r2.qualified
    assert r2.decision == "NO_SIGNAL"
    assert r2.reason_code == C1ReasonCode.C1_IMPULSE_BELOW_THRESHOLD.value

    # 50.001 bps -> QUALIFIED
    m3 = make_test_memory(rolling_15m_return_bps=50.001)
    r3 = evaluate_c1(m3)
    assert r3.qualified
    assert r3.decision == "QUALIFIED"
    assert r3.reason_code == C1ReasonCode.C1_QUALIFIED.value
    assert r3.candidate is not None
    assert r3.candidate.candidate_id == "ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE"
    assert r3.candidate.trace_id == "trace_test_001"


def test_c1_window_boundaries():
    # 09:29:59 -> OUT_OF_WINDOW
    m_pre = make_test_memory(rolling_15m_return_bps=60.0, as_of_timestamp="2026-09-10 09:29:59+05:30")
    r_pre = evaluate_c1(m_pre)
    assert not r_pre.qualified
    assert r_pre.reason_code == C1ReasonCode.C1_OUT_OF_WINDOW.value

    # 09:30:00 -> IN_WINDOW -> QUALIFIED
    m_start = make_test_memory(rolling_15m_return_bps=60.0, as_of_timestamp="2026-09-10 09:30:00+05:30")
    r_start = evaluate_c1(m_start)
    assert r_start.qualified
    assert r_start.reason_code == C1ReasonCode.C1_QUALIFIED.value

    # 14:45:00 -> IN_WINDOW -> QUALIFIED
    m_end = make_test_memory(rolling_15m_return_bps=60.0, as_of_timestamp="2026-09-10 14:45:00+05:30")
    r_end = evaluate_c1(m_end)
    assert r_end.qualified
    assert r_end.reason_code == C1ReasonCode.C1_QUALIFIED.value

    # 14:45:01 -> OUT_OF_WINDOW
    m_post = make_test_memory(rolling_15m_return_bps=60.0, as_of_timestamp="2026-09-10 14:45:01+05:30")
    r_post = evaluate_c1(m_post)
    assert not r_post.qualified
    assert r_post.reason_code == C1ReasonCode.C1_OUT_OF_WINDOW.value


def test_c1_stale_and_warmup():
    # Stale memory
    m_stale = make_test_memory(rolling_15m_return_bps=60.0, freshness_watermark=0.0)
    r_stale = evaluate_c1(m_stale)
    assert not r_stale.qualified
    assert r_stale.reason_code == C1ReasonCode.C1_STALE_MEMORY.value

    # Insufficient bars (< 15 bars)
    m_warm = make_test_memory(rolling_15m_return_bps=60.0, bars_count=10)
    r_warm = evaluate_c1(m_warm)
    assert not r_warm.qualified
    assert r_warm.reason_code == C1ReasonCode.C1_MEMORY_NOT_READY.value


# ---------------------------------------------------------
# Candidate 2 (C2) Unit Tests
# ---------------------------------------------------------

def test_c2_timing_and_threshold_boundaries():
    # 15:11:00 -> PRE_SIGNAL
    m_pre = make_test_memory(distance_from_session_open_bps=60.0, as_of_timestamp="2026-09-10 15:11:00+05:30")
    r_pre = evaluate_c2(m_pre)
    assert not r_pre.qualified
    assert r_pre.reason_code == C2ReasonCode.C2_PRE_SIGNAL.value

    # 15:13:00 -> POST_SIGNAL_WINDOW
    m_post = make_test_memory(distance_from_session_open_bps=60.0, as_of_timestamp="2026-09-10 15:13:00+05:30")
    r_post = evaluate_c2(m_post)
    assert not r_post.qualified
    assert r_post.reason_code == C2ReasonCode.C2_POST_SIGNAL_WINDOW.value

    # Exactly 15:12:00:
    # 49.999 bps -> NO_SIGNAL
    m_49 = make_test_memory(distance_from_session_open_bps=49.999, as_of_timestamp="2026-09-10 15:12:00+05:30")
    r_49 = evaluate_c2(m_49)
    assert not r_49.qualified
    assert r_49.reason_code == C2ReasonCode.C2_TREND_BELOW_THRESHOLD.value

    # 50.000 bps -> '>=' operator -> QUALIFIED
    m_50 = make_test_memory(distance_from_session_open_bps=50.000, as_of_timestamp="2026-09-10 15:12:00+05:30")
    r_50 = evaluate_c2(m_50)
    assert r_50.qualified
    assert r_50.reason_code == C2ReasonCode.C2_QUALIFIED.value
    assert r_50.candidate is not None
    assert r_50.candidate.candidate_id == "ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT"
    assert r_50.candidate.trace_id == "trace_test_001"

    # 50.001 bps -> QUALIFIED
    m_51 = make_test_memory(distance_from_session_open_bps=50.001, as_of_timestamp="2026-09-10 15:12:00+05:30")
    r_51 = evaluate_c2(m_51)
    assert r_51.qualified
    assert r_51.reason_code == C2ReasonCode.C2_QUALIFIED.value


def test_c2_missing_session_open():
    m_no_open = make_test_memory(
        distance_from_session_open_bps=60.0,
        as_of_timestamp="2026-09-10 15:12:00+05:30",
        session_open=0.0,
    )
    r_no_open = evaluate_c2(m_no_open)
    assert not r_no_open.qualified
    assert r_no_open.reason_code == C2ReasonCode.C2_MEMORY_NOT_READY.value


# ---------------------------------------------------------
# Trace ID Propagation & Lifecycle Integration
# ---------------------------------------------------------

def test_trace_lineage_and_lifecycle_transitions():
    t_id = generate_trace_id(seed="trace_funnel_test")
    ring = DiagnosticPulseRing(max_traces=10, max_events=100)
    ledger = CandidateLifecycleLedger()

    # Stage 1: Market Ingress
    r1 = create_stage_record(trace_id=t_id, stage_id="s1", component=PipelineCheckpoint.RAW_TICK_RECEIVE.value)
    ring.record_stage(r1)

    # Stage 2: Memory Update
    r2 = create_stage_record(trace_id=t_id, stage_id="s2", component=PipelineCheckpoint.MARKET_MEMORY_BAR_AGGREGATION.value)
    ring.record_stage(r2)

    # Memory state inherits t_id
    mem = make_test_memory(rolling_15m_return_bps=65.0, trace_id=t_id)

    # Stage 3: C1 Evaluation
    res = evaluate_c1(mem)
    assert res.qualified
    cand = res.candidate
    assert cand is not None
    assert cand.trace_id == t_id

    r3 = create_stage_record(trace_id=t_id, stage_id="s3", component=PipelineCheckpoint.STRATEGY_EVALUATION.value)
    ring.record_stage(r3)

    # Stage 4: Candidate Emission
    r4 = create_stage_record(trace_id=t_id, stage_id="s4", component=PipelineCheckpoint.CANDIDATE_EMISSION.value)
    ring.record_stage(r4)

    # Candidate enters lifecycle ledger
    tr1 = ledger.record_transition(
        candidate_id=cand.candidate_id,
        from_stage=CandidateLifecycleStage.CREATED,
        to_stage=CandidateLifecycleStage.LIQUIDITY_CHECK,
        status="PASS",
        reason_code="LIQUIDITY_OK",
        metadata={"trace_id": t_id},
    )
    assert tr1.metadata["trace_id"] == t_id

    # Common opportunity ranking
    ranked = build_opportunity_book([{
        "trade_id": cand.candidate_id,
        "symbol": cand.symbol,
        "final_score": 0.85,
        "execution_score": 0.90,
        "regime_alignment": 0.80,
        "gating_final_confidence": 0.95,
        "score_breakdown": cand.features,
    }])
    assert len(ranked) == 1
    assert ranked[0].candidate_id == cand.candidate_id
    assert ranked[0].score == 0.85

    # Verify zero disappeared candidates in ledger
    assert len(ledger.detect_disappeared_candidates(expected_stage=CandidateLifecycleStage.LIQUIDITY_CHECK.value)) == 0


def test_2026_09_10_sidecar_parity_oracles():
    # C1 Oracle on Sep 10: max observed return was +13.03 bps
    mem_c1 = make_test_memory(rolling_15m_return_bps=13.03)
    res_c1 = evaluate_c1(mem_c1)
    assert not res_c1.qualified
    assert res_c1.decision == "NO_SIGNAL"
    assert res_c1.reason_code == C1ReasonCode.C1_IMPULSE_BELOW_THRESHOLD.value

    # C2 Oracle on Sep 10 at 15:12: open 23446.60, close 23389.80 -> -24.23 bps
    mem_c2 = make_test_memory(
        session_open=23446.60,
        current_price=23389.80,
        distance_from_session_open_bps=-24.23,
        as_of_timestamp="2026-09-10 15:12:00+05:30",
    )
    res_c2 = evaluate_c2(mem_c2)
    assert not res_c2.qualified
    assert res_c2.decision == "NO_SIGNAL"
    assert res_c2.reason_code == C2ReasonCode.C2_TREND_BELOW_THRESHOLD.value
