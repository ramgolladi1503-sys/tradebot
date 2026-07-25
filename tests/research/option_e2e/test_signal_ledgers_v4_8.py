from __future__ import annotations

from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledgers_v4_8.ledger_builder import build_signal_ledgers
from research.option_e2e_recertification_v4.signal_ledgers_v4_8.repo_inventory import load_canonical_strategy_registry, historical_hypotheses
from research.option_e2e_recertification_v4.signal_ledgers_v4_8.strategy_source_registry import build_strategy_source_registry


def test_registry_is_repository_backed() -> None:
    repo = Path(".")
    registry = build_strategy_source_registry(repo)

    assert "COMPRESSION_BREAKOUT" in registry
    assert "VWAP_RECLAIM" in registry
    assert historical_hypotheses(repo)
    assert registry["COMPRESSION_BREAKOUT"].current_implementation_paths
    assert registry["COMPRESSION_BREAKOUT"].implementation_file_hashes
    assert registry["COMPRESSION_BREAKOUT"].current_implementation_commit
    assert registry["PAIRS_ARBITRAGE"].directional_eligibility == "MULTI_ASSET_OR_PAIR"
    assert registry["NO_TRADE_CHOP"].directional_eligibility == "NO_TRADE_FILTER"
    assert registry["SIMPLE_ORB"].source_domain in {"CURRENT_MASTER_DIAGNOSTIC", "HELPER_OR_AGGREGATE", "HISTORICAL_STRATEGY_IMPLEMENTATION"}
    assert registry["HTF_OPENING_DRIVE_CONT"].directional_eligibility == "HELPER_OR_AGGREGATE" or registry["HTF_OPENING_DRIVE_CONT"].directional_eligibility == "IMPLEMENTATION_MISSING"


def test_builder_reports_registry_and_stays_fail_closed() -> None:
    repo = Path(".")
    ledgers, summary, detail = build_signal_ledgers(repo)

    assert ledgers == []
    assert summary["oracle_verdict"] == "NO_SIGNALS_UNDER_FROZEN_CONTRACT"
    assert summary["lane_count"] >= 18
    assert "runtime/strategy_validation" in " ".join(detail["discovery"]["searched_roots"])
    assert detail["oracle"]["verdict"] == "NO_SIGNALS_UNDER_FROZEN_CONTRACT"
