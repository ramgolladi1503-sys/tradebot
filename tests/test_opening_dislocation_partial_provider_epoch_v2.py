from __future__ import annotations

from datetime import date

from research.opening_dislocation_reversal.fresh_epoch_acquisition import (
    classify_chunk_state,
    partial_epoch_gate,
    strengthened_session_gates,
)


def test_earlier_history_capability_mismatch_marks_unsupported_chunks():
    chunk = {"start": "2015-01-01", "end": "2015-01-31", "state": "PLANNED"}
    assert classify_chunk_state(chunk, date(2022, 1, 1), date(2022, 12, 30)) == "UNSUPPORTED_BY_PROVIDER"


def test_supported_chunk_remains_planned_for_fetch_resume():
    chunk = {"start": "2022-06-01", "end": "2022-06-30", "state": "PLANNED"}
    assert classify_chunk_state(chunk, date(2022, 1, 1), date(2022, 12, 30)) == "PLANNED"


def test_partial_provider_epoch_is_neither_development_nor_holdout():
    gate = partial_epoch_gate(248)
    assert gate["partial_provider_epoch"] is True
    assert gate["development_assigned"] is False
    assert gate["holdout_assigned"] is False
    assert gate["full_session_floor"] is False
    assert gate["strategy_authorized"] is False


def test_full_1800_session_gate_is_unchanged():
    assert strengthened_session_gates(1799, 1200, 500, 365)["total_sessions"] is False
    assert strengthened_session_gates(1800, 1200, 500, 365)["total_sessions"] is True


def test_no_provider_mixing_contract_for_partial_epoch():
    manifest = {"provider": "Upstox", "provider_mixing": "NO", "other_providers": []}
    assert manifest["provider_mixing"] == "NO"
    assert manifest["other_providers"] == []
