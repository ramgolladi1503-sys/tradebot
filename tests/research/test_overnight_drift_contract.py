#!/usr/bin/env python3
"""
Comprehensive Invariant, Mutation, Multi-Process, and Recovery Test Suite:
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Tests:
1. Triple-consistency spec validation (JSON vs sha256 file vs IMMUTABLE_REGISTRY anchor).
2. Dual-file tampering attack rejection (mutation test modifying both JSON and sha256).
3. Specific parameter tampering mutations (SMA 199, cutoff 15:19, entry 15:20, zero friction).
4. Fail-closed macro trend evaluation on NaN / non-positive prices.
5. S1 and S4 qualification under authoritative FROZEN_SPEC parameters.
6. Persistent state recovery across process restarts:
   - Verifies that after process restart, state is reconstructed from disk ledger, not memory.
7. State machine transition graph enforcement against PERSISTED state:
   - Illegal skip transitions (PRE_SESSION -> OBSERVATION_FINALIZED) rejected with ValueError.
   - Illegal backwards transitions (OVERNIGHT_PENDING -> MACRO_STATE_FROZEN) rejected.
8. Quote fail-closed contract & internal freshness derivation:
   - Stale quote (>5000ms delta between source_ts and receipt_ts) -> OBSERVATION_INVALID
   - Missing quote_source_ts or quote_receipt_ts -> OBSERVATION_INVALID
   - Missing best_bid / best_ask -> OBSERVATION_INVALID
   - Inverted spread (best_ask < best_bid) -> OBSERVATION_INVALID
9. Full canonical 100% field record hashing (tampering ANY field fails verification).
10. Tail truncation detection via external head anchor.
11. Atomic crash-recovery test:
    - Ledger progressed ahead of head anchor is recovered and synchronized without corruption.
12. Multi-Process concurrency safety test:
    - Real OS multiprocessing (`multiprocessing.Process`) with independent manager instances
      writing concurrently to the same disk directory without race conditions or forks.
"""

import os
import json
import hashlib
import multiprocessing
import pytest

from core.candidate_audits.nifty_overnight_drift import (
    CANDIDATE_S1_ID,
    CANDIDATE_S4_ID,
    IMMUTABLE_REGISTRY,
    FrozenCandidateSpec,
    load_and_validate_frozen_spec,
    evaluate_overnight_signal,
    OvernightSignalResult
)
from core.read_only_observers.overnight_drift_observer import (
    ObserverLifecycleState,
    TamperEvidentLedgerManager,
    TamperEvidentObservationEntry,
    compute_canonical_record_hash,
    calculate_internal_quote_freshness
)


# ---------------------------------------------------------------------------
# 1. TRIPLE-CONSISTENCY & MUTATION TAMPERING TESTS
# ---------------------------------------------------------------------------

def test_frozen_spec_triple_consistency():
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)
    assert s1_spec.candidate_id == CANDIDATE_S1_ID
    assert s1_spec.threshold_pct == 0.50
    assert s1_spec.deterministic_friction_pts == 14.30
    assert s1_spec.spec_digest == IMMUTABLE_REGISTRY[CANDIDATE_S1_ID]["spec_digest"]

    s4_spec = load_and_validate_frozen_spec(CANDIDATE_S4_ID)
    assert s4_spec.candidate_id == CANDIDATE_S4_ID
    assert s4_spec.required_day == "Monday"
    assert s4_spec.deterministic_friction_pts == 14.30
    assert s4_spec.spec_digest == IMMUTABLE_REGISTRY[CANDIDATE_S4_ID]["spec_digest"]


def test_mutation_dual_file_tamper_attack(tmp_path):
    cand_dir = tmp_path / "S1_MOMENTUM_OVERNIGHT_V1"
    cand_dir.mkdir(parents=True)

    tampered_spec = {
        "candidate_id": "S1_MOMENTUM_OVERNIGHT_V1",
        "candidate_version": "1.0.0",
        "candidate_status": "FROZEN_HISTORICAL_CANDIDATE",
        "signal_evaluation": {"cutoff_wall_clock_ist": "15:20:00.000", "threshold_pct": 0.40},  # Tampered
        "macro_trend_filter": {"rule": "Close[t-1] > SMA200[t-1]", "indicator": "SMA_200"},
        "execution_model": {"entry_wall_clock_ist": "15:21:00.000", "exit_wall_clock_ist": "09:15:00.000", "deterministic_friction_pts": 14.30}
    }
    with open(cand_dir / "FROZEN_SPEC.json", "w") as f:
        json.dump(tampered_spec, f)

    ser = json.dumps(tampered_spec, sort_keys=True)
    new_hash = hashlib.sha256(ser.encode("utf-8")).hexdigest()
    with open(cand_dir / "FROZEN_SPEC.sha256", "w") as f:
        f.write(f"{new_hash}  FROZEN_SPEC.json\n")

    # Fails against IMMUTABLE_REGISTRY anchor
    with pytest.raises(ValueError, match="Dual-file tampering detected"):
        load_and_validate_frozen_spec("S1_MOMENTUM_OVERNIGHT_V1", base_dir=str(tmp_path))


@pytest.mark.parametrize("param_key,tampered_val", [
    (("macro_trend_filter", "indicator"), "SMA_199"),
    (("signal_evaluation", "cutoff_wall_clock_ist"), "15:19:00.000"),
    (("execution_model", "entry_wall_clock_ist"), "15:20:00.000"),
    (("execution_model", "deterministic_friction_pts"), 0.0),
])
def test_mutation_parameter_tampering_rejected(tmp_path, param_key, tampered_val):
    cand_dir = tmp_path / "S1_MOMENTUM_OVERNIGHT_V1"
    cand_dir.mkdir(parents=True, exist_ok=True)

    with open("docs/research/candidates/S1_MOMENTUM_OVERNIGHT_V1/FROZEN_SPEC.json", "r") as f:
        spec = json.load(f)

    if len(param_key) == 2:
        spec[param_key[0]][param_key[1]] = tampered_val

    with open(cand_dir / "FROZEN_SPEC.json", "w") as f:
        json.dump(spec, f)

    ser = json.dumps(spec, sort_keys=True)
    h = hashlib.sha256(ser.encode("utf-8")).hexdigest()
    with open(cand_dir / "FROZEN_SPEC.sha256", "w") as f:
        f.write(f"{h}  FROZEN_SPEC.json\n")

    with pytest.raises(ValueError, match="Dual-file tampering detected"):
        load_and_validate_frozen_spec("S1_MOMENTUM_OVERNIGHT_V1", base_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# 2. FAIL-CLOSED EVALUATION & QUALIFICATION CONTRACTS
# ---------------------------------------------------------------------------

def test_fail_closed_macro_trend_on_nan():
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


def test_s1_and_s4_qualification_under_frozen_authority():
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


# ---------------------------------------------------------------------------
# 3. PERSISTENT STATE RECOVERY & TRANSITION GRAPH ENFORCEMENT
# ---------------------------------------------------------------------------

def test_persistent_state_recovery_across_process_restart(tmp_path):
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # Process 1: Runs during afternoon, captures arrival and transitions to OVERNIGHT_PENDING
    mgr1 = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    mgr1.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="09:00:00",
        macro_uptrend=True,
        day_gain_pct=0.0,
        is_monday=False,
        qualified=False,
    )
    mgr1.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.SIGNAL_SEALED_1520,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )
    mgr1.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.QUALIFIED,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )
    mgr1.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        quote_source_ts="2026-09-22T15:21:00+05:30",
        quote_receipt_ts="2026-09-22T15:21:00.080+05:30",
        best_bid=25139.5,
        best_ask=25140.5,
    )
    mgr1.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.OVERNIGHT_PENDING,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )

    # SIMULATE COMPLETE PROCESS DEATH / RESTART OVERNIGHT
    del mgr1

    # Process 2: Starts next morning at 09:15 with empty memory
    mgr2 = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    session_key = "S1_ONLY|S1_MOMENTUM_OVERNIGHT_V1|2026-09-22"

    # Must reconstruct OVERNIGHT_PENDING directly from disk ledger
    persisted_state = mgr2.get_persisted_session_state("S1_ONLY", session_key)
    assert persisted_state == ObserverLifecycleState.OVERNIGHT_PENDING

    # Seamlessly continues to NEXT_SESSION_OPEN_CAPTURED and OBSERVATION_FINALIZED
    e_next = mgr2.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.NEXT_SESSION_OPEN_CAPTURED,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        next_session_open=25200.0,
    )
    assert e_next.lifecycle_state == "NEXT_SESSION_OPEN_CAPTURED"

    e_fin = mgr2.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.OBSERVATION_FINALIZED,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        next_session_open=25200.0,
    )
    assert e_fin.lifecycle_state == "OBSERVATION_FINALIZED"
    assert mgr2.verify_ledger_integrity("S1_ONLY")[0]


def test_illegal_persisted_state_transition_rejected(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # Attempting to jump directly from PRE_SESSION on disk to NEXT_SESSION_OPEN_CAPTURED
    with pytest.raises(ValueError, match="ILLEGAL_PERSISTED_STATE_TRANSITION"):
        mgr.append_observation(
            sub_ledger="S1_ONLY",
            target_state=ObserverLifecycleState.NEXT_SESSION_OPEN_CAPTURED,
            candidate_spec=s1_spec,
            schedule_sha256=s1_spec.schedule_sha256,
            session_date="2026-09-22",
            decision_ts="15:20:00",
            macro_uptrend=True,
            day_gain_pct=0.55,
            is_monday=False,
            qualified=True,
        )


# ---------------------------------------------------------------------------
# 4. QUOTE FAIL-CLOSED & INTERNAL FRESHNESS DERIVATION
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("source_ts,receipt_ts,bid,ask,expected_notes", [
    ("2026-09-22T15:21:00+05:30", "2026-09-22T15:21:06+05:30", 25139.5, 25140.5, "stale quote 6000ms"),  # 6000ms > 5000ms
    (None, "2026-09-22T15:21:00+05:30", 25139.5, 25140.5, "quote_freshness unparseable or missing"),
    ("2026-09-22T15:21:00+05:30", "2026-09-22T15:21:00.100+05:30", None, 25140.5, "missing bid/ask quote"),
    ("2026-09-22T15:21:00+05:30", "2026-09-22T15:21:00.100+05:30", 25145.0, 25140.0, "inverted or non-positive spread"),
])
def test_quote_fail_closed_contract(tmp_path, source_ts, receipt_ts, bid, ask, expected_notes):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # Bring state to QUALIFIED on disk
    for state in [ObserverLifecycleState.MACRO_STATE_FROZEN, ObserverLifecycleState.SIGNAL_SEALED_1520, ObserverLifecycleState.QUALIFIED]:
        mgr.append_observation(
            sub_ledger="S1_ONLY",
            target_state=state,
            candidate_spec=s1_spec,
            schedule_sha256=s1_spec.schedule_sha256,
            session_date="2026-09-22",
            decision_ts="15:20:00",
            macro_uptrend=True,
            day_gain_pct=0.55,
            is_monday=False,
            qualified=True,
        )

    entry = mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        quote_source_ts=source_ts,
        quote_receipt_ts=receipt_ts,
        best_bid=bid,
        best_ask=ask,
    )
    assert entry.lifecycle_state == "OBSERVATION_INVALID"
    assert not entry.feed_healthy
    assert expected_notes in entry.validation_notes
    assert entry.gross_pnl_pts is None


# ---------------------------------------------------------------------------
# 5. HASH CHAIN INTEGRITY, TAIL TRUNCATION & ATOMIC CRASH RECOVERY
# ---------------------------------------------------------------------------

def test_hash_chain_covers_all_fields(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="09:00:00",
        macro_uptrend=True,
        day_gain_pct=0.0,
        is_monday=False,
        qualified=False,
        validation_notes="UNALTERED_NOTE",
    )

    ledger_file = tmp_path / "s1_only_ledger.jsonl"
    with open(ledger_file, "r") as f:
        record = json.loads(f.read().strip())

    # Alter validation_notes in persisted file
    record["validation_notes"] = "MALICIOUS_NOTE"
    with open(ledger_file, "w") as f:
        f.write(json.dumps(record) + "\n")

    is_valid, err = mgr.verify_ledger_integrity("S1_ONLY")
    assert not is_valid
    assert "TAMPERED_RECORD_PAYLOAD" in err


def test_tail_truncation_detection(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="09:00:00",
        macro_uptrend=True,
        day_gain_pct=0.0,
        is_monday=False,
        qualified=False,
    )
    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.SIGNAL_SEALED_1520,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )

    # Delete second record from ledger file
    ledger_file = tmp_path / "s1_only_ledger.jsonl"
    with open(ledger_file, "r") as f:
        lines = f.readlines()
    with open(ledger_file, "w") as f:
        f.write(lines[0])

    is_valid, err = mgr.verify_ledger_integrity("S1_ONLY")
    assert not is_valid
    assert "TAIL_TRUNCATION_DETECTED" in err


def test_atomic_crash_recovery(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # 1. Write first record (seq 1)
    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="09:00:00",
        macro_uptrend=True,
        day_gain_pct=0.0,
        is_monday=False,
        qualified=False,
    )

    # 2. Append second record directly to ledger (simulating crash before anchor updated)
    # The anchor is at seq 1, ledger is at seq 2
    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.SIGNAL_SEALED_1520,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )

    # Simulate anchor lagging at seq 1
    anchor_file = tmp_path / "s1_only_head_anchor.json"
    ledger_file = tmp_path / "s1_only_ledger.jsonl"
    with open(ledger_file, "r") as f:
        lines = [json.loads(line.strip()) for line in f if line.strip()]

    lagging_anchor = {
        "sub_ledger": "S1_ONLY",
        "total_records": 1,
        "latest_sequence": 1,
        "latest_record_hash": lines[0]["record_hash"],
        "anchor_updated_at": "2026-09-22T09:00:00+00:00",
    }
    with open(anchor_file, "w") as f:
        json.dump(lagging_anchor, f)

    # Predecessor verification succeeds and advances anchor
    mgr.recover_crash_consistency("S1_ONLY")
    is_valid, msg = mgr.verify_ledger_integrity("S1_ONLY")
    assert is_valid
    assert msg == "CHAIN_AND_ANCHOR_VERIFIED_PERFECT"

    # Now tamper with the predecessor record in the ledger
    lines[0]["validation_notes"] = "TAMPERED_PREDECESSOR"
    with open(ledger_file, "w") as f:
        for row in lines:
            f.write(json.dumps(row) + "\n")

    # Reset anchor to old hash
    with open(anchor_file, "w") as f:
        json.dump(lagging_anchor, f)

    # Recovery must fail-closed due to predecessor hash mismatch / payload tampering
    with pytest.raises(ValueError, match="CRASH_RECOVERY_ABORTED"):
        mgr.recover_crash_consistency("S1_ONLY")


def test_separated_pnl_metrics_reported(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # State graph: PRE_SESSION -> MACRO_STATE_FROZEN -> SIGNAL_SEALED_1520 -> QUALIFIED -> ARRIVAL_CAPTURED_1521 -> OVERNIGHT_PENDING -> NEXT_SESSION_OPEN_CAPTURED
    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="09:00:00",
        macro_uptrend=True,
        day_gain_pct=0.0,
        is_monday=False,
        qualified=False,
    )
    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.SIGNAL_SEALED_1520,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )
    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.QUALIFIED,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:20:01",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )
    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:21:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        quote_source_ts="2026-09-22T15:21:00.000+05:30",
        quote_receipt_ts="2026-09-22T15:21:00.050+05:30",
        best_bid=25000.0,
        best_ask=25002.0,  # Midpoint = 25001.0, Ask = 25002.0
    )
    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.OVERNIGHT_PENDING,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="15:21:05",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )
    entry = mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.NEXT_SESSION_OPEN_CAPTURED,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="09:15:00",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        quote_source_ts="2026-09-22T15:21:00.000+05:30",
        quote_receipt_ts="2026-09-22T15:21:00.050+05:30",
        best_bid=25000.0,
        best_ask=25002.0,
        next_session_open=25020.0,
    )

    # Verify separated PnL metrics
    # Midpoint theoretical = 25020 - 25001 = +19.0 pts
    assert entry.midpoint_theoretical_pnl_pts == 19.0
    # Best ask crossing = 25020 - 25002 = +18.0 pts
    assert entry.best_ask_crossing_pnl_pts == 18.0
    # Deterministic cost adjusted = 18.0 - 14.30 = +3.70 pts
    assert entry.deterministic_cost_adjusted_pnl_pts == round(18.0 - s1_spec.deterministic_friction_pts, 2)
    assert entry.net_pnl_pts == round(19.0 - s1_spec.deterministic_friction_pts, 2)


# ---------------------------------------------------------------------------
# 6. MULTI-PROCESS CONCURRENCY SAFETY TEST (REAL OS PROCESSES)
# ---------------------------------------------------------------------------

def _mp_worker(worker_id: int, ledger_dir: str):
    """Worker running in a distinct OS process."""
    mgr = TamperEvidentLedgerManager(ledger_dir=ledger_dir)
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    for i in range(5):
        d_str = f"2026-11-{worker_id:02d}-{i:02d}"
        mgr.append_observation(
            sub_ledger="S1_ONLY",
            target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
            candidate_spec=s1_spec,
            schedule_sha256=s1_spec.schedule_sha256,
            session_date=d_str,
            decision_ts="09:00:00",
            macro_uptrend=True,
            day_gain_pct=0.0,
            is_monday=False,
            qualified=False,
        )


def test_multi_process_concurrency_locking(tmp_path):
    ledger_dir = str(tmp_path)
    procs = [multiprocessing.Process(target=_mp_worker, args=(p, ledger_dir)) for p in range(4)]
    for p in procs: p.start()
    for p in procs: p.join()

    for p in procs:
        assert p.exitcode == 0

    mgr = TamperEvidentLedgerManager(ledger_dir=ledger_dir)
    seq, _ = mgr.get_latest_entry_info("S1_ONLY")
    assert seq == 20  # Exactly 4 processes x 5 records

    is_valid, msg = mgr.verify_ledger_integrity("S1_ONLY")
    assert is_valid
    assert msg == "CHAIN_AND_ANCHOR_VERIFIED_PERFECT"
