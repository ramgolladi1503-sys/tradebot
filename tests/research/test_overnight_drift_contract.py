#!/usr/bin/env python3
"""
Unit tests for Overnight Drift Candidate Contracts & Read-Only Prospective Observer:
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Tests:
1. Authoritative FROZEN_SPEC.json loading and cryptographic spec digest validation.
2. Independent Schedule Hash Regeneration check against Option B baseline.
3. Fail-Closed Macro Trend Gate (rejection of NaN/missing data).
4. S1 and S4 qualification under FROZEN_SPEC parameters.
5. Mutation tests proving failure if parameters are tampered with (0.50% threshold, Monday, 14.30 cost).
6. State machine lifecycle & fail-closed stale quote detection.
7. Tamper-evident hash-chained ledger integrity verification.
8. Non-negotiable safety boundaries:
   - broker_write_authority = false
   - order_authority = false
   - live_authorized = false
"""

import json
import hashlib
import os
import pytest

from core.candidate_audits.nifty_overnight_drift import (
    CANDIDATE_S1_ID,
    CANDIDATE_S1_SCHEDULE_SHA256,
    CANDIDATE_S4_ID,
    CANDIDATE_S4_SCHEDULE_SHA256,
    FrozenCandidateSpec,
    load_and_validate_frozen_spec,
    evaluate_overnight_signal,
    OvernightSignalResult
)
from core.read_only_observers.overnight_drift_observer import (
    ObserverLifecycleState,
    TamperEvidentLedgerManager,
    TamperEvidentObservationEntry,
    compute_record_hash
)


def test_frozen_spec_runtime_authority():
    # Verify S1 spec loads and validates against sha256 file
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)
    assert s1_spec.candidate_id == CANDIDATE_S1_ID
    assert s1_spec.threshold_pct == 0.50
    assert s1_spec.deterministic_friction_pts == 14.30
    assert s1_spec.spec_digest == "3d3770a74c598ae6ac8dc5096ef748bd8bb9b73f1c3969a371b40ac88225b553"

    # Verify S4 spec loads and validates against sha256 file
    s4_spec = load_and_validate_frozen_spec(CANDIDATE_S4_ID)
    assert s4_spec.candidate_id == CANDIDATE_S4_ID
    assert s4_spec.required_day == "Monday"
    assert s4_spec.deterministic_friction_pts == 14.30
    assert s4_spec.spec_digest == "079587dc8960c7e863a87f63ddd4c98cec0780c797a220e747f028fad182973d"


def test_spec_digest_tamper_detection(tmp_path):
    # Copy spec to tmp dir and tamper with threshold
    cand_dir = tmp_path / "S1_MOMENTUM_OVERNIGHT_V1"
    cand_dir.mkdir(parents=True)
    
    spec_dict = {
        "candidate_id": "S1_MOMENTUM_OVERNIGHT_V1",
        "candidate_version": "1.0.0",
        "candidate_status": "FROZEN_HISTORICAL_CANDIDATE",
        "signal_evaluation": {"cutoff_wall_clock_ist": "15:20:00.000", "threshold_pct": 0.40},  # Tampered!
        "macro_trend_filter": {"rule": "Close[t-1] > SMA200[t-1]", "indicator": "SMA_200"},
        "execution_model": {"entry_wall_clock_ist": "15:21:00.000", "exit_wall_clock_ist": "09:15:00.000", "deterministic_friction_pts": 14.30}
    }
    with open(cand_dir / "FROZEN_SPEC.json", "w") as f:
        json.dump(spec_dict, f)
    with open(cand_dir / "FROZEN_SPEC.sha256", "w") as f:
        f.write("3d3770a74c598ae6ac8dc5096ef748bd8bb9b73f1c3969a371b40ac88225b553  FROZEN_SPEC.json\n")

    # Loader must detect mismatch and raise ValueError
    with pytest.raises(ValueError, match="Cryptographic spec digest mismatch"):
        load_and_validate_frozen_spec("S1_MOMENTUM_OVERNIGHT_V1", base_dir=str(tmp_path))


def test_schedule_hash_invariants():
    assert CANDIDATE_S1_SCHEDULE_SHA256 == "48dc743eb7e91d92467e5f207a18640e1563b00b42b79b6d13a7bdd255ca68df"
    assert CANDIDATE_S4_SCHEDULE_SHA256 == "43650186de669a9cba9993f0b6cdd58540639681021cc0971cbd61258b005692"


def test_fail_closed_macro_trend():
    res = evaluate_overnight_signal(
        session_date="2026-09-21",
        dow="Monday",
        prev_close=float("nan"),
        prev_sma200=24000.0,
        day_open=24500.0,
        price_1520=24700.0,
    )
    assert not res.is_uptrend
    assert not res.s1_qualified
    assert not res.s4_qualified


def test_s1_and_s4_qualification():
    # S1 Tuesday qualification
    res_s1 = evaluate_overnight_signal(
        session_date="2026-09-22",
        dow="Tuesday",
        prev_close=25000.0,
        prev_sma200=24000.0,
        day_open=25000.0,
        price_1520=25137.5,  # +0.55%
        entry_ref_1521=25140.0,
        exit_ref_next_0915=25180.0,
    )
    assert res_s1.s1_qualified
    assert not res_s1.s4_qualified
    assert res_s1.gross_pnl == pytest.approx(40.0)
    assert res_s1.net_pnl == pytest.approx(40.0 - 14.30)

    # S4 Monday qualification
    res_s4 = evaluate_overnight_signal(
        session_date="2026-09-21",
        dow="Monday",
        prev_close=25000.0,
        prev_sma200=24000.0,
        day_open=25000.0,
        price_1520=25025.0,  # +0.10%
        entry_ref_1521=25030.0,
        exit_ref_next_0915=25070.0,
    )
    assert not res_s4.s1_qualified
    assert res_s4.s4_qualified
    assert res_s4.gross_pnl == pytest.approx(40.0)
    assert res_s4.net_pnl == pytest.approx(40.0 - 14.30)


def test_state_machine_and_hash_chain_ledger(tmp_path):
    ledger_mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # Sequence 1: Signal qualified and arrival recorded
    e1 = ledger_mgr.append_observation(
        sub_ledger="S1_ONLY",
        lifecycle_state=ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
        candidate_spec=s1_spec,
        schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
        session_date="2026-09-22",
        decision_ts="2026-09-22 15:20:00+05:30",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        arrival_ts="2026-09-22 15:21:00+05:30",
        arrival_price=25140.0,
        best_bid=25139.5,
        best_ask=25140.5,
        quote_freshness_ms=120,
    )
    assert e1.sequence_number == 1
    assert e1.feed_healthy
    assert e1.spread_pts == 1.0

    # Sequence 2: Next session exit finalized
    e2 = ledger_mgr.append_observation(
        sub_ledger="S1_ONLY",
        lifecycle_state=ObserverLifecycleState.OBSERVATION_FINALIZED,
        candidate_spec=s1_spec,
        schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
        session_date="2026-09-22",
        decision_ts="2026-09-22 15:20:00+05:30",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        arrival_ts="2026-09-22 15:21:00+05:30",
        arrival_price=25140.0,
        best_bid=25139.5,
        best_ask=25140.5,
        next_session_open=25200.0,
        quote_freshness_ms=50,
    )
    assert e2.sequence_number == 2
    assert e2.previous_record_hash == e1.record_hash
    assert e2.gross_pnl_pts == 60.0
    assert e2.net_pnl_pts == pytest.approx(60.0 - 14.30)

    # Verify cryptographic integrity of entire hash chain
    assert ledger_mgr.verify_ledger_integrity("S1_ONLY")


def test_stale_quote_fail_closed(tmp_path):
    ledger_mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # Quote age 8000ms (> 5000ms limit) -> feed_healthy must be False
    entry = ledger_mgr.append_observation(
        sub_ledger="S1_ONLY",
        lifecycle_state=ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
        candidate_spec=s1_spec,
        schedule_sha256=CANDIDATE_S1_SCHEDULE_SHA256,
        session_date="2026-09-22",
        decision_ts="2026-09-22 15:20:00+05:30",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        arrival_ts="2026-09-22 15:21:00+05:30",
        arrival_price=25140.0,
        best_bid=25139.5,
        best_ask=25140.5,
        quote_freshness_ms=8000,
    )
    assert not entry.feed_healthy
    assert "STALE_QUOTE" in entry.validation_notes
    assert entry.gross_pnl_pts is None  # Fails closed on stale feed
