from __future__ import annotations

from core.runtime_candidate_handoff_root_cause import build_candidate_handoff_root_cause_payload


def test_candidate_handoff_payload_counts_missing_identity_and_duplicates():
    payload = build_candidate_handoff_root_cause_payload(
        cycle_ts_epoch=123.0,
        strategy_generated_count=5,
        phase2_raw_candidates=[
            {"trade_id": "T1", "symbol": "NIFTY", "instrument_token": 111, "strike": 20000, "expiry": "2026-01-01"},
            {"trade_id": "T1", "symbol": "NIFTY", "instrument_token": 111, "strike": 20000, "expiry": "2026-01-01"},
            {"trade_id": "", "symbol": "NIFTY", "instrument_token": None, "strike": None, "expiry": ""},
        ],
        phase2_ranked_count=1,
    )
    assert payload["strategy_generated_count"] == 5
    assert payload["phase2_raw_count"] == 3
    assert payload["pre_phase2_drop_count"] == 2
    assert payload["missing_trade_id_count"] == 1
    assert payload["missing_instrument_token_count"] == 1
    assert payload["missing_strike_count"] == 1
    assert payload["missing_expiry_count"] == 1
    assert payload["duplicate_count"] == 1
    assert payload["duplicate_key_counts"]


def test_candidate_handoff_payload_counts_unresolved_contract_and_fallback():
    payload = build_candidate_handoff_root_cause_payload(
        cycle_ts_epoch=123.0,
        strategy_generated_count=2,
        phase2_raw_candidates=[
            {
                "trade_id": "T2",
                "symbol": "NIFTY",
                "instrument_token": 222,
                "strike": 20000,
                "expiry": "2026-01-01",
                "hard_blockers": ["UNRESOLVED_CONTRACT"],
            },
            {
                "trade_id": "T3",
                "symbol": "NIFTY",
                "instrument_token": 223,
                "strike": 20100,
                "expiry": "2026-01-01",
                "synthetic_candidate": True,
                "source_flags": {"recovered_fallback": True},
            },
        ],
        phase2_ranked_count=0,
    )
    assert payload["unresolved_contract_count"] == 1
    assert payload["fallback_candidate_count"] == 1
    assert payload["recovered_fallback_candidate_count"] == 1

