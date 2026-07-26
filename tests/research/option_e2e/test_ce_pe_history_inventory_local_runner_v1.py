from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.run_ce_pe_history_inventory_local import run


def test_local_runner_rebuilds_manifest_and_remains_no_go(
    tmp_path: Path,
) -> None:
    campaign = tmp_path / "campaign"
    data_dir = campaign / "runtime" / "market_data" / "20260714"
    data_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "ts": [1_783_555_200.0],
            "instrument_key": ["NSE_FO|1"],
            "bid_price": [9.9],
            "ask_price": [10.1],
        }
    ).to_parquet(data_dir / "combined.parquet", index=False)

    result = run(
        campaign_worktree=campaign,
        output_root=tmp_path / "external-output",
    )

    assert result["source_universe_oracle"] == "AGREEMENT"
    assert result["run_a_primary_oracle"] == "AGREEMENT"
    assert result["run_b_primary_oracle"] == "AGREEMENT"
    assert result["run_a_run_b_byte_determinism"] == "PASS"
    assert result["valid_option_session_dates"] == ["2026-07-09"]
    assert result["coverage_candidate_found"] is False
    assert result["strategy_development_authorized"] is False
    assert result["next_decision"] == (
        "MORE_CE_PE_HISTORY_REQUIRED_OR_DEEP_CANDIDATE_REVIEW"
    )
    assert result["outcomes_read"] is False
    assert result["pnl_read"] is False
    assert result["holdout_outcomes_read"] is False
    assert result["backtests_run"] is False
