from __future__ import annotations

import pandas as pd

from scripts.run_mac_all_strategy_option_pf_campaign import (
    CANONICAL_STRATEGIES,
    RESEARCH_HYPOTHESES,
    build_blocked_analytics,
    build_session_matrix,
    inspect_replay_root,
    write_outputs,
)


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path)


def test_actual_files_drive_session_discovery_and_counts_change(tmp_path) -> None:
    root = tmp_path / "replay"
    _write(
        root / "2026-07-01" / "underlying" / "NIFTY_2026-07-01.parquet",
        [{"date": "2026-07-01 09:15:00+05:30", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}],
    )
    inventory, _, _, _ = inspect_replay_root(root)
    matrix, underlying, option, partition = build_session_matrix(inventory)
    inventory_count = sum(1 for _ in inventory)
    assert inventory_count == 1
    assert underlying["usable_underlying_session_count"] == 1
    assert option["valid_option_session_count"] == 0
    assert matrix[0]["campaign_usable"] is False
    assert partition["ordered_session_universe"] == []

    _write(
        root / "2026-07-01" / "underlying" / "NIFTY 100 CE 30 JUL 26.parquet",
        [{"timestamp": "2026-07-01 09:16:00+05:30", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}],
    )
    inventory, _, _, _ = inspect_replay_root(root)
    matrix, _, option, partition = build_session_matrix(inventory)
    inventory_count = sum(1 for _ in inventory)
    assert inventory_count == 2
    assert option["valid_option_session_count"] == 1
    assert partition["ordered_session_universe"] == ["2026-07-01"]
    assert any(row["campaign_usable"] for row in matrix)


def test_five_minute_underlying_files_classify_as_five_minute(tmp_path) -> None:
    root = tmp_path / "replay"
    _write(
        root / "2026-07-01" / "underlying" / "NIFTY_2026-07-01.parquet",
        [{"date": "2026-07-01 09:15:00+05:30", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1, "instrument": "NIFTY", "interval": "5minute"}],
    )
    inventory, schema_groups, _, _ = inspect_replay_root(root)
    assert inventory[0]["classification"] == "UNDERLYING_5M_OHLCV"
    assert schema_groups[0]["classifications"] == {"UNDERLYING_5M_OHLCV": 1}


def test_committed_summary_json_cannot_create_a_session(tmp_path) -> None:
    root = tmp_path / "replay"
    root.mkdir()
    (root / "ce_pe_replay_readiness_summary.json").write_text('{"valid_option_dates":["2099-01-01"]}', encoding="utf-8")
    inventory, _, coverage, _ = inspect_replay_root(root)
    matrix, underlying, option, partition = build_session_matrix(inventory)
    assert inventory == []
    assert coverage == []
    assert matrix == []
    assert underlying["usable_underlying_session_count"] == 0
    assert option["valid_option_session_count"] == 0
    assert partition["ordered_session_universe"] == []


def test_zero_price_and_identityless_option_files_are_classified_unusable(tmp_path) -> None:
    root = tmp_path / "replay"
    _write(
        root / "20260701" / "options" / "NIFTY_OPT_MOCK_ltp.parquet",
        [{"timestamp": "2026-07-01 09:15:00+05:30", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0}],
    )
    inventory, _, _, rejections = inspect_replay_root(root)
    assert inventory[0]["classification"] in {"ZERO_PRICE_PLACEHOLDER", "UNKNOWN"}
    assert rejections
    _, _, option, _ = build_session_matrix(inventory)
    assert option["valid_option_session_count"] == 0


def test_positive_identified_option_ohlc_and_ltp_ticks_classify_as_price_authority(tmp_path) -> None:
    root = tmp_path / "replay"
    _write(
        root / "2026-07-01" / "underlying" / "NIFTY 100 CE 30 JUL 26.parquet",
        [{"timestamp": "2026-07-01 09:16:00+05:30", "open": 10, "high": 12, "low": 9, "close": 11, "volume": 10}],
    )
    _write(
        root / "2026-07-01" / "underlying" / "NIFTY 100 PE 30 JUL 26.parquet",
        [{"ts": "2026-07-01 09:17:00+05:30", "ltp": 8, "symbol": "NIFTY 100 PE 30 JUL 26", "token": 1, "vol": 1}],
    )
    inventory, _, _, _ = inspect_replay_root(root)
    classes = {row["classification"] for row in inventory}
    assert "OPTION_1M_OHLCV" in classes
    assert "OPTION_LTP_TICKS" in classes
    _, _, option, _ = build_session_matrix(inventory)
    assert option["valid_option_session_count"] == 1


def test_candidate_rows_are_not_mistaken_for_option_prices(tmp_path) -> None:
    root = tmp_path / "replay"
    _write(root / "2026-07-01" / "signals.parquet", [{"strategy_id": "SIMPLE_ORB", "signal_ts": "2026-07-01 09:30:00+05:30", "direction": "bullish"}])
    inventory, _, _, _ = inspect_replay_root(root)
    assert inventory[0]["classification"] == "STRATEGY_CANDIDATE_ROWS"
    _, _, option, partition = build_session_matrix(inventory)
    assert option["valid_option_session_count"] == 0
    assert partition["ordered_session_universe"] == []


def test_blocked_analytics_contains_every_required_lane() -> None:
    rows = build_blocked_analytics("KITE_REPLAY_HAS_NO_USABLE_OPTION_PRICE_AUTHORITY")
    ids = {row["entity_id"] for row in rows}

    assert ids == set(CANONICAL_STRATEGIES) | set(RESEARCH_HYPOTHESES)
    assert sum(1 for row in rows if row["strategy_hypothesis_class"] == "CANONICAL_STRATEGY") == 12
    assert sum(1 for row in rows if row["strategy_hypothesis_class"] == "FROZEN_RESEARCH_HYPOTHESIS") == 11
    assert all(row["final_verdict"] == "DATA_BLOCKED" for row in rows)
    assert all(row["trades"] == 0 for row in rows)
    assert all(row["profit_factor"] is None for row in rows)
    assert all(row["holdout_profit_factor"] == "SEALED" for row in rows)
    assert all(row["allowed_for_live_execution"] is False for row in rows)


def test_write_outputs_publishes_repaired_artifacts(tmp_path) -> None:
    analytics = build_blocked_analytics("KITE_REPLAY_HAS_NO_USABLE_OPTION_PRICE_AUTHORITY")
    manifest = write_outputs(
        tmp_path,
        inventory=[],
        rejected=[],
        matrix=[],
        underlying={"usable_underlying_session_count": 0},
        option={"valid_option_session_count": 0},
        partition={"ordered_session_universe": [], "holdout_dates": []},
        analytics=analytics,
    )

    assert manifest["final_verdict"] == "DATA_REASSESSMENT_IN_PROGRESS"
    assert (tmp_path / "kite_candidate_replay_inventory.json").exists()
    assert (tmp_path / "trade_ledger_all_strategies.parquet").exists()
    assert "all_strategy_option_master_analytics.json" in manifest["artifact_hashes"]
