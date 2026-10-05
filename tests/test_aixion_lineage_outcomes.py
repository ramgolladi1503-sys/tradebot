from __future__ import annotations

from scripts.generate_offline_fixture import build_fixture
from aixion_trade_intelligence.lineage import build_candidate_lineage
from aixion_trade_intelligence.outcomes import calculate_outcomes
from aixion_trade_intelligence.replay import replay


def test_candidate_lineage_is_joined_end_to_end():
    ordered = replay(build_fixture()).ordered_events
    rows = build_candidate_lineage(ordered)
    row, = rows
    assert row.strategy_id == "OFFLINE_CAUSAL_CONTRACT"
    assert row.selected_option_instrument == "NSE_FO|OFFLINE_ATM_CE"
    assert row.approval_decision == "APPROVED"
    assert row.fill_count == 1
    assert row.filled_quantity == 65
    assert row.average_fill_price == 102.0


def test_outcomes_use_causal_ask_and_bid():
    ordered = replay(build_fixture()).ordered_events
    lineage = build_candidate_lineage(ordered)
    outcomes = calculate_outcomes(ordered, lineage)
    assert [row.horizon_seconds for row in outcomes] == [30, 90, 270]
    first = outcomes[0]
    assert first.option_entry_ask == 102.0
    assert first.option_exit_bid == 104.0
    assert first.option_executable_pnl == 2.0
    assert first.signed_underlying_return > 0
    assert first.classification == "FULL_TRADE_CORRECT"
    assert first.label_available_time > first.decision_time
