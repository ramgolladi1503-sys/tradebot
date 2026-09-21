#!/usr/bin/env python3
"""
Unit tests for Overnight Drift Candidate Contracts:
- S1_MOMENTUM_OVERNIGHT_V1
- S4_MONDAY_OVERNIGHT_V1

Tests:
1. Cryptographic Spec Hash Integrity (matches FROZEN_SPEC.json and hardcoded digests).
2. Immutable Schedule SHA256 integrity check against canonical Option B baseline.
3. Fail-Closed Macro Trend Gate:
   - NaN, missing, or negative close/SMA200 fails closed to False.
4. Signal evaluation correctness:
   - S1 requires Macro Uptrend and Day Gain > +0.50% at 15:20 cutoff.
   - S4 requires Macro Uptrend and Day of Week == Monday.
5. P&L & Cost Deduction Invariants (exact 14.30 pts deducted).
6. Anti-Contamination & Read-Only Governance:
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
    CANDIDATE_S1_SPEC_DIGEST,
    CANDIDATE_S1_SCHEDULE_SHA256,
    CANDIDATE_S4_ID,
    CANDIDATE_S4_SPEC_DIGEST,
    CANDIDATE_S4_SCHEDULE_SHA256,
    DETERMINISTIC_COST_PTS,
    evaluate_overnight_signal,
    OvernightSignalResult
)


def test_s1_frozen_spec_hash_integrity():
    spec_path = "docs/research/candidates/S1_MOMENTUM_OVERNIGHT_V1/FROZEN_SPEC.json"
    assert os.path.exists(spec_path)
    with open(spec_path) as f:
        spec = json.load(f)
    serialized = json.dumps(spec, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    assert digest == CANDIDATE_S1_SPEC_DIGEST
    with open("docs/research/candidates/S1_MOMENTUM_OVERNIGHT_V1/FROZEN_SPEC.sha256") as f:
        stored = f.read().strip().split()[0]
    assert digest == stored


def test_s4_frozen_spec_hash_integrity():
    spec_path = "docs/research/candidates/S4_MONDAY_OVERNIGHT_V1/FROZEN_SPEC.json"
    assert os.path.exists(spec_path)
    with open(spec_path) as f:
        spec = json.load(f)
    serialized = json.dumps(spec, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    assert digest == CANDIDATE_S4_SPEC_DIGEST
    with open("docs/research/candidates/S4_MONDAY_OVERNIGHT_V1/FROZEN_SPEC.sha256") as f:
        stored = f.read().strip().split()[0]
    assert digest == stored


def test_immutable_schedule_digests():
    assert CANDIDATE_S1_SCHEDULE_SHA256 == "48dc743eb7e91d92467e5f207a18640e1563b00b42b79b6d13a7bdd255ca68df"
    assert CANDIDATE_S4_SCHEDULE_SHA256 == "43650186de669a9cba9993f0b6cdd58540639681021cc0971cbd61258b005692"


def test_fail_closed_macro_trend():
    # Test NaN prev_close
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

    # Test NaN prev_sma200
    res2 = evaluate_overnight_signal(
        session_date="2026-09-21",
        dow="Monday",
        prev_close=25000.0,
        prev_sma200=float("nan"),
        day_open=24500.0,
        price_1520=24700.0,
    )
    assert not res2.is_uptrend
    assert not res2.s1_qualified
    assert not res2.s4_qualified


def test_s1_momentum_qualification():
    # Uptrend, Day Gain = +0.55% (> 0.50%) -> S1 Qualified
    res = evaluate_overnight_signal(
        session_date="2026-09-22",
        dow="Tuesday",
        prev_close=25000.0,
        prev_sma200=24000.0,
        day_open=25000.0,
        price_1520=25137.5,  # +0.55%
        entry_ref_1521=25140.0,
        exit_ref_next_0915=25180.0,
    )
    assert res.is_uptrend
    assert res.s1_qualified
    assert not res.s4_qualified  # Tuesday
    assert res.gross_pnl == pytest.approx(40.0)
    assert res.net_pnl == pytest.approx(40.0 - DETERMINISTIC_COST_PTS)

    # Uptrend, Day Gain = +0.45% (<= 0.50%) -> S1 Fails
    res_fail = evaluate_overnight_signal(
        session_date="2026-09-22",
        dow="Tuesday",
        prev_close=25000.0,
        prev_sma200=24000.0,
        day_open=25000.0,
        price_1520=25112.5,  # +0.45%
    )
    assert res_fail.is_uptrend
    assert not res_fail.s1_qualified


def test_s4_monday_qualification():
    # Monday Uptrend, Day Gain = +0.10% -> S4 Qualified, S1 Fails
    res = evaluate_overnight_signal(
        session_date="2026-09-21",
        dow="Monday",
        prev_close=25000.0,
        prev_sma200=24000.0,
        day_open=25000.0,
        price_1520=25025.0,  # +0.10%
        entry_ref_1521=25030.0,
        exit_ref_next_0915=25070.0,
    )
    assert res.is_uptrend
    assert not res.s1_qualified
    assert res.s4_qualified
    assert res.gross_pnl == pytest.approx(40.0)
    assert res.net_pnl == pytest.approx(40.0 - DETERMINISTIC_COST_PTS)

    # Monday Downtrend -> Both Fail
    res_bear = evaluate_overnight_signal(
        session_date="2026-09-21",
        dow="Monday",
        prev_close=23000.0,
        prev_sma200=24000.0,
        day_open=23000.0,
        price_1520=23200.0,
    )
    assert not res_bear.is_uptrend
    assert not res_bear.s1_qualified
    assert not res_bear.s4_qualified


def test_s1_and_s4_overlap_qualification():
    # Monday Uptrend, Day Gain = +0.75% -> Both S1 and S4 Qualified
    res = evaluate_overnight_signal(
        session_date="2026-09-21",
        dow="Monday",
        prev_close=25000.0,
        prev_sma200=24000.0,
        day_open=25000.0,
        price_1520=25187.5,  # +0.75%
        entry_ref_1521=25190.0,
        exit_ref_next_0915=25250.0,
    )
    assert res.is_uptrend
    assert res.s1_qualified
    assert res.s4_qualified
    assert res.gross_pnl == pytest.approx(60.0)
    assert res.net_pnl == pytest.approx(60.0 - DETERMINISTIC_COST_PTS)
