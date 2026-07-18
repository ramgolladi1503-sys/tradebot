from research.strategy_outcomes.adapters.opening_range_retest import candidate_from_orb_ledger_row


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
