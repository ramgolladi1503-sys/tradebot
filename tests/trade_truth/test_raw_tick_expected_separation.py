"""Tests for raw-tick causal replay expected output separation."""

from pathlib import Path
import pytest
from core.trade_truth.raw_tick_causal_replay import (
    RawTickSessionStore,
    run_raw_tick_replay,
    compare_replay_to_expected,
)


def test_expected_output_does_not_influence_replay_execution():
    p_raw = Path("/Volumes/TradeBotData/live market capture/2026-09-10/upstox_full_ticks_20260910_stitched.parquet")
    if not p_raw.exists():
        pytest.skip("External raw tick capture not mounted")

    store = RawTickSessionStore(p_raw, "2026-09-10")

    input_b = {
        "trace_id": "test_trace_separation",
        "session_date": "2026-09-10",
        "timestamp": "2026-09-10 09:36:00+05:30",
        "warmup_status": "WARMUP_COMPLETE",
        "raw_tick_source": str(p_raw),
        "historical_sha": "f2ca8c899424d404b3e607047b767929df012272",
    }

    # 1. Run replay with input bundle
    actual1 = run_raw_tick_replay(input_b, session_store=store)
    hashes1 = dict(actual1.stage_hashes)

    # 2. Compare with original expected output
    exp_normal = {"c1_qualified": False, "c1_reason": "C1_IMPULSE_BELOW_THRESHOLD"}
    comp1 = compare_replay_to_expected(actual1, exp_normal)

    # 3. Materially corrupt expected output
    exp_corrupted = {
        "c1_qualified": True,
        "c1_reason": "CORRUPTED_ADVERSARIAL_REASON",
        "random_field": 999999,
    }

    # 4. Run replay again independently
    actual2 = run_raw_tick_replay(input_b, session_store=store)
    hashes2 = dict(actual2.stage_hashes)

    # 5. Compare actual2 with corrupted expected output
    comp2 = compare_replay_to_expected(actual2, exp_corrupted)

    # Replay actual hashes MUST remain 100% identical regardless of expected output
    assert hashes1 == hashes2
    assert actual1 == actual2

    # Comparisons reflect the divergence in expected output without mutating actuals
    assert comp1.terminal_status == "PARTIAL_PARITY"
    assert comp2.terminal_status == "DIVERGED"
    assert comp1.stage_hashes == comp2.stage_hashes
