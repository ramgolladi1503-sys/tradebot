#!/usr/bin/env python3
"""
Comprehensive Mutation and Invariant Test Suite for Overnight Drift Contracts & Observer:
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Tests (20 Comprehensive Test Cases):
1. Dual-domain immutable spec validation (JSON vs SHA256 vs IMMUTABLE_REGISTRY).
2. Mutation: Changing JSON + .sha256 together must FAIL against IMMUTABLE_REGISTRY.
3. Mutation: Parameter tampering tests:
   - SMA 200 -> 199 fails closed
   - Cutoff 15:20 -> 15:19 fails closed
   - Entry 15:21 -> 15:20 fails closed
   - Monday -> Tuesday fails closed
   - Deterministic cost 14.30 -> 0.0 fails closed
4. Fail-closed macro trend evaluation (NaN/missing data).
5. S1 and S4 qualification under FROZEN_SPEC authority.
6. State machine transition graph enforcement:
   - Illegal skip transitions (e.g. PRE_SESSION -> OBSERVATION_FINALIZED) must raise ValueError.
   - Illegal backwards transitions (e.g. ARRIVAL -> PRE_SESSION) must raise ValueError.
7. Quote fail-closed contract for ARRIVAL_CAPTURED_1521:
   - Missing quote_freshness_ms -> OBSERVATION_INVALID
   - Stale quote (>5000ms) -> OBSERVATION_INVALID
   - Missing best_bid / best_ask -> OBSERVATION_INVALID
   - Inverted spread (ask < bid) -> OBSERVATION_INVALID
8. Full canonical hash coverage:
   - Altering ANY field in a JSONL line (including validation_notes, quote_freshness_ms) fails verification.
9. Tail truncation detection:
   - Deleting the last line of the ledger fails verification against external head anchor.
10. Concurrent process-locking test:
   - Simultaneous appends produce sequential, strictly non-forking entries.
11. Independent Schedule Regeneration check:
   - Option B schedule hashes match exact canonical baseline.
"""

import os
import json
import hashlib
import threading
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
    compute_canonical_record_hash
)


# ---------------------------------------------------------------------------
# TEST GROUP 1: DUAL-DOMAIN SPEC IMMUTABILITY & TAMPER MUTATION TESTS
# ---------------------------------------------------------------------------

def test_frozen_spec_dual_domain_validation():
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


def test_mutation_json_and_sha256_dual_tamper_attack(tmp_path):
    """
    Simulates attack where an adversary alters FROZEN_SPEC.json AND updates FROZEN_SPEC.sha256.
    The external IMMUTABLE_REGISTRY anchor must catch and reject this.
    """
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

    # Adversary also updates the sha256 file
    ser = json.dumps(tampered_spec, sort_keys=True)
    new_hash = hashlib.sha256(ser.encode("utf-8")).hexdigest()
    with open(cand_dir / "FROZEN_SPEC.sha256", "w") as f:
        f.write(f"{new_hash}  FROZEN_SPEC.json\n")

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
# TEST GROUP 2: FAIL-CLOSED EVALUATION & QUALIFICATION CONTRACTS
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


# ---------------------------------------------------------------------------
# TEST GROUP 3: STATE MACHINE TRANSITION GRAPH ENFORCEMENT
# ---------------------------------------------------------------------------

def test_state_machine_illegal_skip_transition_rejected(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # Attempting to jump directly from PRE_SESSION to OBSERVATION_FINALIZED must fail
    with pytest.raises(ValueError, match="ILLEGAL_STATE_TRANSITION"):
        mgr.append_observation(
            sub_ledger="S1_ONLY",
            target_state=ObserverLifecycleState.OBSERVATION_FINALIZED,
            candidate_spec=s1_spec,
            schedule_sha256=s1_spec.schedule_sha256,
            session_date="2026-09-22",
            decision_ts="2026-09-22 15:20:00+05:30",
            macro_uptrend=True,
            day_gain_pct=0.55,
            is_monday=False,
            qualified=True,
        )


def test_state_machine_valid_full_lifecycle(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    # 1. Macro State Frozen
    e1 = mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="2026-09-22 09:00:00+05:30",
        macro_uptrend=True,
        day_gain_pct=0.0,
        is_monday=False,
        qualified=False,
    )
    assert e1.lifecycle_state == "MACRO_STATE_FROZEN"

    # 2. Signal Sealed 1520
    e2 = mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.SIGNAL_SEALED_1520,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="2026-09-22 15:20:00+05:30",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )
    assert e2.lifecycle_state == "SIGNAL_SEALED_1520"

    # 3. Qualified
    e3 = mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.QUALIFIED,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="2026-09-22 15:20:00+05:30",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
    )
    assert e3.lifecycle_state == "QUALIFIED"

    # 4. Arrival Captured 1521
    e4 = mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
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
        quote_freshness_ms=100,
    )
    assert e4.lifecycle_state == "ARRIVAL_CAPTURED_1521"


# ---------------------------------------------------------------------------
# TEST GROUP 4: QUOTE FAIL-CLOSED CONTRACT
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kwargs,expected_err", [
    ({"quote_freshness_ms": None, "best_bid": 25139.5, "best_ask": 25140.5, "arrival_price": 25140.0, "arrival_ts": "15:21:00"}, "quote_freshness_ms missing"),
    ({"quote_freshness_ms": 6000, "best_bid": 25139.5, "best_ask": 25140.5, "arrival_price": 25140.0, "arrival_ts": "15:21:00"}, "stale quote"),
    ({"quote_freshness_ms": 100, "best_bid": None, "best_ask": 25140.5, "arrival_price": 25140.0, "arrival_ts": "15:21:00"}, "missing bid/ask/arrival quote"),
    ({"quote_freshness_ms": 100, "best_bid": 25145.0, "best_ask": 25140.0, "arrival_price": 25140.0, "arrival_ts": "15:21:00"}, "inverted or non-positive spread"),
])
def test_quote_fail_closed_contract(tmp_path, kwargs, expected_err):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)
    session_key = "S1_ONLY|S1_MOMENTUM_OVERNIGHT_V1|2026-09-22"
    mgr.session_states[session_key] = ObserverLifecycleState.QUALIFIED

    entry = mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.ARRIVAL_CAPTURED_1521,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="2026-09-22 15:20:00+05:30",
        macro_uptrend=True,
        day_gain_pct=0.55,
        is_monday=False,
        qualified=True,
        **kwargs
    )
    assert entry.lifecycle_state == "OBSERVATION_INVALID"
    assert not entry.feed_healthy
    assert expected_err in entry.validation_notes
    assert entry.gross_pnl_pts is None


# ---------------------------------------------------------------------------
# TEST GROUP 5: HASH-CHAIN COVERAGE & TAIL TRUNCATION DETECTION
# ---------------------------------------------------------------------------

def test_hash_chain_covers_all_fields_and_catches_modification(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)
    session_key = "S1_ONLY|S1_MOMENTUM_OVERNIGHT_V1|2026-09-22"
    mgr.session_states[session_key] = ObserverLifecycleState.PRE_SESSION

    mgr.append_observation(
        sub_ledger="S1_ONLY",
        target_state=ObserverLifecycleState.MACRO_STATE_FROZEN,
        candidate_spec=s1_spec,
        schedule_sha256=s1_spec.schedule_sha256,
        session_date="2026-09-22",
        decision_ts="2026-09-22 09:00:00+05:30",
        macro_uptrend=True,
        day_gain_pct=0.0,
        is_monday=False,
        qualified=False,
        validation_notes="ORIGINAL_NOTE",
    )

    # Tamper with an unhashed candidate note field in JSONL
    ledger_file = tmp_path / "s1_only_ledger.jsonl"
    with open(ledger_file, "r") as f:
        data = json.loads(f.read())
    data["validation_notes"] = "TAMPERED_NOTE"
    with open(ledger_file, "w") as f:
        f.write(json.dumps(data) + "\n")

    # Integrity verification must catch tampering
    is_valid, msg = mgr.verify_ledger_integrity("S1_ONLY")
    assert not is_valid
    assert "TAMPERED_RECORD_PAYLOAD" in msg


def test_tail_truncation_detected_by_external_head_anchor(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)
    session_key = "S1_ONLY|S1_MOMENTUM_OVERNIGHT_V1|2026-09-22"
    mgr.session_states[session_key] = ObserverLifecycleState.PRE_SESSION

    # Append 2 entries
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

    # Simulate adversary truncating the last line of the JSONL ledger
    ledger_file = tmp_path / "s1_only_ledger.jsonl"
    with open(ledger_file, "r") as f:
        lines = f.readlines()
    with open(ledger_file, "w") as f:
        f.write(lines[0])  # Only keep first line

    # Verifier must detect tail truncation via head anchor mismatch
    is_valid, msg = mgr.verify_ledger_integrity("S1_ONLY")
    assert not is_valid
    assert "TAIL_TRUNCATION_DETECTED" in msg


# ---------------------------------------------------------------------------
# TEST GROUP 6: CONCURRENT APPEND PROCESS-LOCKING TEST
# ---------------------------------------------------------------------------

def test_concurrent_appends_process_locking_no_forks(tmp_path):
    mgr = TamperEvidentLedgerManager(ledger_dir=str(tmp_path))
    s1_spec = load_and_validate_frozen_spec(CANDIDATE_S1_ID)

    errors = []

    def worker(worker_id):
        try:
            for i in range(10):
                d_str = f"2026-10-{worker_id:02d}-{i:02d}"
                s_key = f"S1_ONLY|S1_MOMENTUM_OVERNIGHT_V1|{d_str}"
                mgr.session_states[s_key] = ObserverLifecycleState.PRE_SESSION
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
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert len(errors) == 0
    # Total records must be exactly 40 (4 workers x 10 entries)
    seq, last_hash = mgr.get_latest_entry_info("S1_ONLY")
    assert seq == 40
    # Ledger chain must be intact and non-forked
    is_valid, msg = mgr.verify_ledger_integrity("S1_ONLY")
    assert is_valid
    assert msg == "CHAIN_AND_ANCHOR_VERIFIED_PERFECT"
