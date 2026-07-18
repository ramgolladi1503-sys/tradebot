from research.strategy_outcomes.adapters.opening_range_retest import (
    bars_from_ohlcv_rows,
    candidate_from_orb_ledger_row,
    canonical_outcome_records_hash,
)


def test_orb_adapter_maps_signal_timestamp_to_proposal_ready_at():
    candidate = candidate_from_orb_ledger_row(
        {
            "candidate_hash": "abc",
            "session_key": "2026-01-01:NIFTY",
            "symbol": "NIFTY",
            "direction": "BUY_CALL",
            "signal_timestamp": "2026-01-01T09:31:00+05:30",
        }
    )
    assert candidate.proposal_ready_at == "2026-01-01T09:31:00+05:30"


def test_orb_adapter_maps_certified_ledger_shape():
    candidate = candidate_from_orb_ledger_row(
        {
            "setup_id": "setup-1",
            "session_date": "2024-05-30",
            "symbol": "NIFTY",
            "direction": "BUY_PUT",
            "proposal_ready_at_iso": "2024-05-30T09:42:00+05:30",
            "history_hash": "history-1",
            "semantic_payload": {
                "setup_id": "setup-1",
                "symbol": "NIFTY",
                "direction": "BUY_PUT",
                "proposal_ready_at_iso": "2024-05-30T09:42:00+05:30",
            },
        }
    )
    assert candidate.candidate_id == "setup-1"
    assert candidate.session_key == "2024-05-30:NIFTY"
    assert candidate.proposal_ready_at == "2024-05-30T09:42:00+05:30"
    assert candidate.source_hash == "history-1"


def test_bars_from_ohlcv_rows_canonicalizes_local_timestamps():
    bars = bars_from_ohlcv_rows(
        [
            {"timestamp": "2024-05-30 09:16:00", "open": 101, "high": 102, "low": 100, "close": 101},
            {"timestamp": "2024-05-30 09:15:00", "open": 100, "high": 101, "low": 99, "close": 100},
        ],
        session_key="2024-05-30:NIFTY",
    )
    assert [bar.timestamp for bar in bars] == ["2024-05-30T09:15:00+05:30", "2024-05-30T09:16:00+05:30"]


def test_canonical_outcome_records_hash_ignores_order():
    left = [{"candidate_id": "b", "status": "MEASURED"}, {"candidate_id": "a", "status": "MEASURED"}]
    right = [{"candidate_id": "a", "status": "MEASURED"}, {"candidate_id": "b", "status": "MEASURED"}]
    assert canonical_outcome_records_hash(left) == canonical_outcome_records_hash(right)
