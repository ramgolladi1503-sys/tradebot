import pandas as pd
import pytest

from research.strategy_outcomes.contract import OutcomeCandidate
from research.strategy_outcomes.engine import (
    apply_overlap,
    horizon_terminal_index,
    legal_entry_index,
    measure_candidate,
    parse_timestamp,
    source_prefix_hash,
)


def _frame():
    return pd.DataFrame(
        [
            {"timestamp": "2026-01-01 09:42:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5},
            {"timestamp": "2026-01-01 09:43:00", "open": 101.0, "high": 104.0, "low": 100.0, "close": 103.0},
            {"timestamp": "2026-01-01 09:44:00", "open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0},
            {"timestamp": "2026-01-01 09:45:00", "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0},
        ]
    )


def test_parse_timestamp_rejects_naive_candidate_time():
    with pytest.raises(ValueError):
        parse_timestamp("2026-01-01T09:42:00")


def test_elapsed_horizon_uses_entry_bar_close_for_one_minute():
    frame = _frame()
    entry_index = legal_entry_index(frame, parse_timestamp("2026-01-01T09:42:00+05:30"))
    assert entry_index == 1
    expected, terminal_index = horizon_terminal_index(frame, entry_index, 1)
    assert expected.isoformat() == "2026-01-01T09:43:00+05:30"
    assert terminal_index == 1


def test_source_prefix_hash_ignores_future_mutation_after_proposal():
    frame = _frame()
    proposal = parse_timestamp("2026-01-01T09:43:00+05:30")
    baseline = source_prefix_hash(frame, proposal)
    mutated = frame.copy()
    mutated.loc[3, "close"] = 999.0
    assert source_prefix_hash(mutated, proposal) == baseline


def test_measure_candidate_records_directional_mfe_mae_and_horizon_status():
    candidate = OutcomeCandidate("c1", "2026-01-01:NIFTY", "NIFTY", "BUY_CALL", "2026-01-01T09:42:00+05:30", "s", "c1")
    source = type(
        "Source",
        (),
        {
            "logical_path": "logical",
            "sha256": "sha",
            "byte_size": 1,
            "row_count": 4,
            "frame": _frame(),
        },
    )()
    record = measure_candidate(candidate, source=source, stop_return=0.01, target_return=0.02)
    assert record["candidate_status"] == "MEASURED"
    assert record["horizons"]["1"]["actual_terminal_timestamp"] == "2026-01-01T09:43:00+05:30"
    assert record["horizons"]["1"]["forward_return"] == pytest.approx((103.0 - 101.0) / 101.0)
    assert record["horizons"]["1"]["mfe"] == pytest.approx((104.0 - 101.0) / 101.0)
    assert record["horizons"]["1"]["mae"] == pytest.approx((100.0 - 101.0) / 101.0)


def test_overlap_half_open_adjacent_is_not_overlap():
    records = [
        {
            "candidate_id": "a",
            "candidate_status": "MEASURED",
            "session_key": "s",
            "symbol": "NIFTY",
            "direction": "BUY_CALL",
            "legal_entry_timestamp": "2026-01-01T09:43:00+05:30",
            "maximum_legal_horizon": 1,
        },
        {
            "candidate_id": "b",
            "candidate_status": "MEASURED",
            "session_key": "s",
            "symbol": "NIFTY",
            "direction": "BUY_CALL",
            "legal_entry_timestamp": "2026-01-01T09:44:00+05:30",
            "maximum_legal_horizon": 1,
        },
    ]
    summary = apply_overlap(records)
    assert summary["same_direction_overlapping_pairs"] == 0
    assert records[0]["overlap_count"] == 0


def test_overlap_counts_same_and_opposite_direction_pairs():
    records = [
        {
            "candidate_id": "a",
            "candidate_status": "MEASURED",
            "session_key": "s",
            "symbol": "NIFTY",
            "direction": "BUY_CALL",
            "legal_entry_timestamp": "2026-01-01T09:43:00+05:30",
            "maximum_legal_horizon": 5,
        },
        {
            "candidate_id": "b",
            "candidate_status": "MEASURED",
            "session_key": "s",
            "symbol": "NIFTY",
            "direction": "BUY_PUT",
            "legal_entry_timestamp": "2026-01-01T09:44:00+05:30",
            "maximum_legal_horizon": 5,
        },
    ]
    summary = apply_overlap(records)
    assert summary["opposite_direction_overlapping_pairs"] == 1
    assert records[0]["opposite_direction_overlap_count"] == 1
