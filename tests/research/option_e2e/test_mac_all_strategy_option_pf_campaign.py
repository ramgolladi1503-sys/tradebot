from __future__ import annotations

from scripts.run_mac_all_strategy_option_pf_campaign import (
    CANONICAL_STRATEGIES,
    RESEARCH_HYPOTHESES,
    build_blocked_analytics,
    write_outputs,
)


def test_blocked_analytics_contains_every_required_lane() -> None:
    rows = build_blocked_analytics("INSUFFICIENT_USABLE_SESSIONS_LT_3")
    ids = {row["entity_id"] for row in rows}

    assert ids == set(CANONICAL_STRATEGIES) | set(RESEARCH_HYPOTHESES)
    assert sum(1 for row in rows if row["strategy_hypothesis_class"] == "CANONICAL_STRATEGY") == 12
    assert sum(1 for row in rows if row["strategy_hypothesis_class"] == "FROZEN_RESEARCH_HYPOTHESIS") == 11
    assert all(row["final_verdict"] == "DATA_BLOCKED" for row in rows)
    assert all(row["trades"] == 0 for row in rows)
    assert all(row["profit_factor"] is None for row in rows)
    assert all(row["holdout_profit_factor"] == "SEALED" for row in rows)
    assert all(row["allowed_for_live_execution"] is False for row in rows)


def test_write_outputs_publishes_all_rows_and_empty_ledger(tmp_path) -> None:
    analytics = build_blocked_analytics("INSUFFICIENT_USABLE_SESSIONS_LT_3")
    manifest = write_outputs(
        tmp_path,
        inventory=[],
        rejected=[],
        matrix=[
            {
                "date": "2026-07-14",
                "underlying": "BANKNIFTY",
                "underlying_candles_available": False,
                "ce_contracts_with_positive_prices": 1,
                "pe_contracts_with_positive_prices": 1,
                "strike_range": "1-1",
                "expiry_labels": "TEST",
                "option_bars_or_ticks": 2,
                "session_catalogue_buildable": True,
                "source": "fixture",
            }
        ],
        underlying={"usable_underlying_session_count": 0},
        option={"valid_option_session_count": 1},
        partition={"ordered_session_universe": ["2026-07-14"], "holdout_dates": []},
        analytics=analytics,
    )

    assert manifest["final_verdict"] == "NO_VALIDATED_PROFITABLE_STRATEGY_FOUND"
    assert manifest["blocker"] == "INSUFFICIENT_USABLE_SESSIONS_LT_3"
    assert (tmp_path / "all_strategy_option_master_analytics.csv").exists()
    assert (tmp_path / "trade_ledger_all_strategies.parquet").exists()
    assert "all_strategy_option_master_analytics.json" in manifest["artifact_hashes"]
    assert sum(1 for _ in manifest["artifact_hashes"]) >= 10
