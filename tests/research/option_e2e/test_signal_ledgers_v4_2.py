from __future__ import annotations

from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_2.build_signal_ledgers import HISTORICAL_RESEARCH_HYPOTHESES, build_signal_ledgers


def test_signal_ledger_marks_all_strategies_and_hypotheses_blocked() -> None:
    records, summary = build_signal_ledgers(Path("research/option_e2e_recertification_v4/inventory_v4_1/historical_strategy_inventory_v4_1.json"))

    assert summary["status_counts"]["SIGNAL_INPUT_DATA_MISSING"] == len(records)
    assert summary["hypothesis_count"] == len(HISTORICAL_RESEARCH_HYPOTHESES)
    assert all(record.status == "SIGNAL_INPUT_DATA_MISSING" for record in records)
