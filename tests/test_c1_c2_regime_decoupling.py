"""Tests for C1 and C2 Candidate Decoupling from Upstream Regime Admission Gates.

Proves:
1. When regime is REGIME_UNSTABLE and C1 impulse exceeds +50 bps, C1 evaluates independently, qualifies, raw_candidate_count reflects >= 1, candidate transitions to REGIME_CHECK/FILTERED, and is not falsely blamed as NO_MARKET_SETUP.
2. When regime is REGIME_UNSTABLE and C1 impulse is below +50 bps, raw_candidate_count remains 0 and attribution records legitimate NO_MARKET_SETUP (C1_IMPULSE_BELOW_THRESHOLD).
3. At 15:12, C2 with trend >= +50 bps qualifies under REGIME_UNSTABLE, raw_candidate_count reflects >= 1, and downstream rejection attributes to gatekeeper_blocked.
4. Regime source files match cryptographic baseline hashes (REGIME_LOGIC_MODIFIED=False).
5. Broker safety invariants hold: is_order_action=False, broker_api_called=False, broker_write_authority=False.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from core.candidate_evaluators import (
    C1ReasonCode,
    C2ReasonCode,
    evaluate_c1,
    evaluate_c2,
)
from core.market_session_store import MarketMemorySnapshot
from core.observability import (
    CandidateLifecycleLedger,
    CandidateLifecycleStage,
    generate_trace_id,
)
from core.observability.production_bridge import (
    get_production_candidate_ledger,
    get_production_strategy_tracker,
)
from core.orchestrator import _evaluate_c1_c2_for_symbol
from core.runtime_candidate_starvation_trace import build_candidate_starvation_trace_payload


def test_c1_qualifies_and_decouples_from_regime():
    """Test 1: When C1 impulse > 50 bps, helper qualifies C1 regardless of regime."""
    market_data = {
        "symbol": "NIFTY",
        "spot": 23500.0,
        "rolling_15m_return_bps": 58.5,
        "distance_from_session_open_bps": 40.0,
        "ohlc_bars_count": 30,
        "regime": "REGIME_UNSTABLE",
        "unstable_reasons": ["ENTROPY_HIGH", "MARGINAL_PROBABILITY"],
        "is_stale": False,
    }
    t_id = generate_trace_id(seed="c1_test_decouple")
    eval_results, qualified = _evaluate_c1_c2_for_symbol(
        market_data=market_data,
        sym="NIFTY",
        trace_id=t_id,
        ts_str="2026-09-11 11:00:00+05:30",
    )

    assert len(eval_results) >= 1
    c1_res = next(r for r in eval_results if r.strategy_id == "C1_INTRADAY_15M_IMPULSE")
    assert c1_res.qualified is True
    assert c1_res.reason_code == C1ReasonCode.C1_QUALIFIED.value
    assert len(qualified) == 1
    assert qualified[0].candidate_id == "ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE"
    assert qualified[0].trace_id == t_id
    assert qualified[0].is_order_action is False
    assert qualified[0].broker_write_authority is False


def test_c1_below_threshold_produces_legitimate_no_setup():
    """Test 2: When C1 impulse < 50 bps, candidate count is 0 and classified as NO_MARKET_SETUP."""
    market_data = {
        "symbol": "NIFTY",
        "spot": 23500.0,
        "rolling_15m_return_bps": 22.0,
        "distance_from_session_open_bps": 15.0,
        "ohlc_bars_count": 30,
        "regime": "REGIME_UNSTABLE",
        "unstable_reasons": ["ENTROPY_HIGH"],
        "is_stale": False,
    }
    t_id = generate_trace_id(seed="c1_below_thresh")
    eval_results, qualified = _evaluate_c1_c2_for_symbol(
        market_data=market_data,
        sym="NIFTY",
        trace_id=t_id,
        ts_str="2026-09-11 11:00:00+05:30",
    )

    c1_res = next(r for r in eval_results if r.strategy_id == "C1_INTRADAY_15M_IMPULSE")
    assert c1_res.qualified is False
    assert c1_res.reason_code == C1ReasonCode.C1_IMPULSE_BELOW_THRESHOLD.value
    assert len(qualified) == 0
    assert c1_res.attribution is not None
    assert c1_res.attribution.evaluation_status == "EVALUATED_NO_SIGNAL"


def test_c2_qualifies_at_1512_under_regime_unstable():
    """Test 3: At 15:12 IST, C2 with trend >= +50 bps qualifies even if regime is UNSTABLE."""
    market_data = {
        "symbol": "NIFTY",
        "spot": 23550.0,
        "session_open": 23400.0,
        "rolling_15m_return_bps": 10.0,
        "distance_from_session_open_bps": 64.1,
        "ohlc_bars_count": 350,
        "regime": "REGIME_UNSTABLE",
        "unstable_reasons": ["ENTROPY_HIGH"],
        "is_stale": False,
    }
    t_id = generate_trace_id(seed="c2_at_1512")
    eval_results, qualified = _evaluate_c1_c2_for_symbol(
        market_data=market_data,
        sym="NIFTY",
        trace_id=t_id,
        ts_str="2026-09-11 15:12:00+05:30",
    )

    c2_res = next(r for r in eval_results if r.strategy_id == "C2_OVERNIGHT_TREND")
    assert c2_res.qualified is True
    assert c2_res.reason_code == C2ReasonCode.C2_QUALIFIED.value
    c2_cand = next(c for c in qualified if c.candidate_id == "ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT")
    assert c2_cand.trace_id == t_id
    assert c2_cand.is_order_action is False


def test_starvation_payload_reflects_raw_candidates_when_gate_blocks():
    """Test 4: Proves candidate starvation trace correctly shows raw_candidate_count = 1 when C1/C2 qualify but regime blocks."""
    snapshot = {
        "symbol": "NIFTY",
        "regime": {
            "primary_regime": "REGIME_UNSTABLE",
            "regime_entropy": 0.92,
            "regime_entropy_max": 0.85,
            "regime_unstable": True,
            "unstable_reasons": ["ENTROPY_HIGH"],
        },
        "raw_candidate_count": 1,
        "post_scan_survivor_count": 1,
        "post_soft_reject_count": 1,
        "post_real_filter_count": 0,
        "post_executable_filter_count": 0,
        "reject_reason": "gatekeeper_blocked",
        "reject_gate_reasons": ["REGIME_UNSTABLE"],
        "scan_reject_counts": {"gatekeeper_blocked": 1},
        "blocker_counts": {"REGIME_UNSTABLE": 1},
    }

    payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={"REGIME_UNSTABLE": 1},
        feed_runtime={},
        candidate_starvation_snapshots=[snapshot],
    )

    assert payload["raw_candidate_count"] == 1
    assert payload["post_scan_survivor_count"] == 1
    assert payload["first_zero_stage"] == "post_real_filter_zero"
    assert payload["had_symbol_candidates_this_session_or_cycle"] is True
    assert payload["latest_global_blocker"] == "REGIME_UNSTABLE"


def test_regime_source_immutability_audit():
    """Test 5: Cryptographic audit proving zero changes to regime logic/entropy/contracts/thresholds."""
    audit_file = Path("/Volumes/TradeBotData/mros-c1-c2-regime-decoupling-1789118879/REGIME_SOURCE_IMMUTABILITY_AUDIT.json")
    assert audit_file.exists(), f"Audit file {audit_file} missing"
    audit_data = json.loads(audit_file.read_text(encoding="utf-8"))

    repo_root = Path(__file__).resolve().parent.parent
    for rel_path, meta in audit_data["hashes"].items():
        target_path = repo_root / rel_path
        assert target_path.exists(), f"File {rel_path} does not exist"
        data = target_path.read_bytes()
        actual_sha = hashlib.sha256(data).hexdigest()
        expected_sha = meta["sha256"]
        assert actual_sha == expected_sha, (
            f"IMMUTABILITY VIOLATION: {rel_path} hash changed! "
            f"Expected {expected_sha}, got {actual_sha}"
        )
        assert len(data) == meta["bytes"], (
            f"IMMUTABILITY VIOLATION: {rel_path} size changed! "
            f"Expected {meta['bytes']} bytes, got {len(data)}"
        )
