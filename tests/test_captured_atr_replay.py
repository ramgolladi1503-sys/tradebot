from __future__ import annotations

from datetime import timedelta

import pytest

from core.session_atr import calculate_session_atr_state
from tests.test_captured_market_session_replay import (
    CORPUS_ROOT,
    _build_state_from_row,
    _checkpoints_for_row,
    _load_candle_rows,
    _selected_replay_corpus,
)


@pytest.mark.parametrize("selection_index", [0, 1])
def test_full_session_replay_produces_causal_short_and_long_atr(selection_index: int) -> None:
    full_rows = [
        item
        for item in _selected_replay_corpus()["rows"]
        if item["suitability_classification"] == "SUITABLE_FULL_UNDERLYING_SESSION"
    ]
    assert len(full_rows) >= 2
    row = full_rows[selection_index]
    rows = _load_candle_rows(CORPUS_ROOT / row["relative_path"])

    first = _build_state_from_row(row, rows[0]["ts"] + timedelta(minutes=1))
    fourth = _build_state_from_row(row, rows[3]["ts"] + timedelta(minutes=1))
    fifth = _build_state_from_row(row, rows[4]["ts"] + timedelta(minutes=1))
    twenty_ninth = _build_state_from_row(row, rows[28]["ts"] + timedelta(minutes=1))
    thirtieth = _build_state_from_row(row, rows[29]["ts"] + timedelta(minutes=1))
    final = _build_state_from_row(row, rows[-1]["ts"] + timedelta(minutes=1))

    first_result = calculate_session_atr_state(first)
    fourth_result = calculate_session_atr_state(fourth)
    fifth_result = calculate_session_atr_state(fifth)
    twenty_ninth_result = calculate_session_atr_state(twenty_ninth)
    thirtieth_result = calculate_session_atr_state(thirtieth)
    final_result = calculate_session_atr_state(final)

    assert first_result.atr_short is None
    assert first_result.atr_long is None
    assert fourth_result.atr_short is None
    assert fourth_result.atr_long is None
    assert fifth_result.short_available is True
    assert fifth_result.long_available is False
    assert twenty_ninth_result.short_available is True
    assert twenty_ninth_result.long_available is False
    assert thirtieth_result.short_available is True
    assert thirtieth_result.long_available is True
    assert final_result.short_available is True
    assert final_result.long_available is True
    assert calculate_session_atr_state(
        first.completed_bar_history,
        symbol=first.symbol,
        session_date=first.session_date,
        timeframe=first.timeframe,
        source_history_hash=first.history_hash,
    ) == first_result
    assert calculate_session_atr_state(
        final.completed_bar_history,
        symbol=final.symbol,
        session_date=final.session_date,
        timeframe=final.timeframe,
        source_history_hash=final.history_hash,
    ) == final_result


def test_partial_session_replay_still_obeys_the_same_contract() -> None:
    row = next(
        item
        for item in _selected_replay_corpus()["rows"]
        if item["suitability_classification"] == "SUITABLE_PARTIAL_UNDERLYING_SESSION"
    )
    checkpoints = _checkpoints_for_row(row)
    final_state = _build_state_from_row(row, checkpoints[-1].cutoff)
    result = calculate_session_atr_state(final_state)

    assert result.contract_version == "atr_short_long_v1"
    assert result.short_available is True
    assert result.long_available is True
    assert result.short_status == "AVAILABLE"
    assert result.long_status == "AVAILABLE"


def test_incremental_and_batch_replay_match_for_prefix_states() -> None:
    row = next(
        item
        for item in _selected_replay_corpus()["rows"]
        if item["suitability_classification"] == "SUITABLE_FULL_UNDERLYING_SESSION"
    )
    checkpoints = _checkpoints_for_row(row)
    states = [_build_state_from_row(row, checkpoint.cutoff) for checkpoint in checkpoints[:5]]

    for state in states:
        batch_result = calculate_session_atr_state(state)
        iterable_result = calculate_session_atr_state(
            state.completed_bar_history,
            symbol=state.symbol,
            session_date=state.session_date,
            timeframe=state.timeframe,
            source_history_hash=state.history_hash,
        )
        assert batch_result == iterable_result
