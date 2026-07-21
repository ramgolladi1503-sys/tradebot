from __future__ import annotations

from datetime import date

import pytest

from research.opening_dislocation_reversal.fresh_epoch_acquisition import (
    month_chunks,
    resolve_unique_nifty_index,
    split_70_30,
    strengthened_session_gates,
    validate_acquisition_contract,
)


def test_monthly_chunk_planning_is_deterministic():
    chunks = month_chunks(date(2015, 1, 1), date(2015, 3, 5))
    assert chunks == [
        {"start": "2015-01-01", "end": "2015-01-31", "state": "PLANNED"},
        {"start": "2015-02-01", "end": "2015-02-28", "state": "PLANNED"},
        {"start": "2015-03-01", "end": "2015-03-05", "state": "PLANNED"},
    ]


def test_strengthened_1800_session_gate():
    assert strengthened_session_gates(1799, 1259, 540, 365)["total_sessions"] is False
    assert all(strengthened_session_gates(1800, 1260, 540, 365).values())


def test_70_30_split_uses_floor_integer_boundary():
    dev, holdout = split_70_30([str(i) for i in range(10)])
    assert dev == ["0", "1", "2", "3", "4", "5", "6"]
    assert holdout == ["7", "8", "9"]


def test_acquisition_contract_rejects_strategy_fields():
    payload = {
        "option_data_allowed": False,
        "broker_trading_api_allowed": False,
        "candidate_counts_allowed": False,
        "strategy_outcomes_allowed": False,
        "dislocation_threshold": 0.1,
    }
    with pytest.raises(ValueError, match="strategy_parameter_fields_forbidden"):
        validate_acquisition_contract(payload)


def test_instrument_ambiguity_fails_closed():
    rows = [
        {"instrument_key": "NSE_INDEX|Nifty 50", "instrument_type": "INDEX", "name": "Nifty 50"},
        {"instrument_key": "NSE_INDEX|Nifty 50", "instrument_type": "INDEX", "name": "Nifty 50"},
    ]
    with pytest.raises(ValueError, match="instrument_resolution_not_unique"):
        resolve_unique_nifty_index(rows)
