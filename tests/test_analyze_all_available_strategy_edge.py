from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import analyze_all_available_strategy_edge as analyzer
from scripts import catalog_available_strategy_data as catalog


def _market(path: Path, instrument: str = "NIFTY", volume: int = 10) -> Path:
    rows = []
    for i in range(80):
        rows.append(
            {
                "date": pd.Timestamp("2026-06-29 09:15:00") + pd.Timedelta(minutes=i),
                "open": 100 + i * 0.05,
                "high": 100.2 + i * 0.05,
                "low": 99.8 + i * 0.05,
                "close": 100.1 + i * 0.05,
                "volume": volume,
                "instrument": instrument,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_option_pnl_blocked_when_option_ltp_missing(tmp_path: Path) -> None:
    _market(tmp_path / "nifty.csv")
    cat = catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    result = analyzer.analyze_catalog(catalog_path=tmp_path / "audit" / "available_data_catalog.csv", out_dir=tmp_path / "audit")
    by_dataset = pd.read_csv(tmp_path / "audit" / "all_available_strategy_edge_by_dataset.csv")
    option_rows = by_dataset[
        (by_dataset["strategy"] == "core.candidate_generator.generate_candidates")
        & (by_dataset["dataset_type"] == "INDEX_OHLC")
        & (by_dataset["dataset_path"].astype(str).str.endswith("nifty.csv"))
    ]

    assert result["safety"]["executable_option_pnl_claim"] is False
    assert result["executable_option_replay_verdict"] == "NOT_EXECUTABLE_OPTION_BACKTEST"
    assert not option_rows.empty
    assert set(option_rows["verdict"]) == {"NOT_EXECUTABLE_OPTION_BACKTEST"}
    assert bool(option_rows["executable_replay_ready"].any()) is False


def test_executable_replay_blocked_when_bid_ask_missing(tmp_path: Path) -> None:
    option_ltp = tmp_path / "option_ltp.csv"
    pd.DataFrame(
        [{"timestamp": "2026-06-29 09:15:00", "tradingsymbol": "NIFTYCE", "strike": 24000, "option_type": "CE", "ltp": 100.0}]
    ).to_csv(option_ltp, index=False)
    cat = catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    analyzer.analyze_catalog(catalog_path=tmp_path / "audit" / "available_data_catalog.csv", out_dir=tmp_path / "audit")
    by_dataset = pd.read_csv(tmp_path / "audit" / "all_available_strategy_edge_by_dataset.csv")

    assert "OPTION_LTP_REPLAY_ONLY" in set(by_dataset["verdict"])
    assert bool(by_dataset["executable_replay_ready"].any()) is False


def test_fallback_advisory_recovered_candidates_remain_non_executable(tmp_path: Path) -> None:
    quote = tmp_path / "option_quote_fallback.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-06-29 09:15:00",
                "candidate_id": "c1",
                "tradingsymbol": "NIFTYCE",
                "strike": 24000,
                "option_type": "CE",
                "ltp": 100.0,
                "bid": 99.0,
                "ask": 101.0,
                "depth": "{}",
                "reason": "fallback advisory recovered",
            }
        ]
    ).to_csv(quote, index=False)
    cat = catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    analyzer.analyze_catalog(catalog_path=tmp_path / "audit" / "available_data_catalog.csv", out_dir=tmp_path / "audit")
    by_dataset = pd.read_csv(tmp_path / "audit" / "all_available_strategy_edge_by_dataset.csv")

    assert bool(by_dataset["executable_replay_ready"].any()) is False


def test_multiple_datasets_aggregate_without_double_counting(tmp_path: Path) -> None:
    _market(tmp_path / "nifty_1.csv", "NIFTY")
    _market(tmp_path / "banknifty_1.csv", "BANKNIFTY")
    cat = catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    analyzer.analyze_catalog(catalog_path=tmp_path / "audit" / "available_data_catalog.csv", out_dir=tmp_path / "audit")
    by_strategy = pd.read_csv(tmp_path / "audit" / "all_available_strategy_edge_by_strategy.csv")

    assert not by_strategy.empty
    assert by_strategy["dataset_count"].max() <= int(len(cat))


def test_max_proxy_datasets_produces_partial_proxy_analysis(tmp_path: Path) -> None:
    _market(tmp_path / "nifty_1.csv", "NIFTY")
    _market(tmp_path / "banknifty_1.csv", "BANKNIFTY")
    catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    result = analyzer.analyze_catalog(
        catalog_path=tmp_path / "audit" / "available_data_catalog.csv",
        out_dir=tmp_path / "audit",
        max_proxy_datasets=1,
    )

    assert result["proxy_analysis_verdict"] == "PARTIAL_PROXY_ANALYSIS"
    assert result["proxy_datasets_available"] >= 1
    assert result["proxy_datasets_skipped_due_to_cap"] >= 1
    assert result["selected_dataset_paths"]
    assert result["skipped_dataset_paths"]


def test_uncapped_run_reports_full_proxy_analysis_when_all_selected(tmp_path: Path) -> None:
    _market(tmp_path / "nifty_1.csv", "NIFTY")
    catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    result = analyzer.analyze_catalog(
        catalog_path=tmp_path / "audit" / "available_data_catalog.csv",
        out_dir=tmp_path / "audit",
        max_proxy_datasets=None,
    )

    assert result["proxy_analysis_verdict"] == "FULL_PROXY_ANALYSIS"
    assert result["proxy_datasets_skipped_due_to_cap"] == 0


def test_no_broker_kite_order_calls_happen(tmp_path: Path) -> None:
    _market(tmp_path / "nifty.csv")
    catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    result = analyzer.analyze_catalog(catalog_path=tmp_path / "audit" / "available_data_catalog.csv", out_dir=tmp_path / "audit")

    assert result["safety"]["broker_api_called"] is False
    assert result["safety"]["is_order_action"] is False
    assert result["safety"]["allowed_for_live_execution"] is False


def test_resume_accumulates_without_duplicate_counting(tmp_path: Path) -> None:
    _market(tmp_path / "nifty_1.csv", "NIFTY")
    _market(tmp_path / "banknifty_1.csv", "BANKNIFTY")
    catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    first = analyzer.analyze_catalog(
        catalog_path=tmp_path / "audit" / "available_data_catalog.csv",
        out_dir=tmp_path / "audit",
        batch_size=1,
    )
    second = analyzer.analyze_catalog(
        catalog_path=tmp_path / "audit" / "available_data_catalog.csv",
        out_dir=tmp_path / "audit",
        batch_size=1,
        resume=1,
    )
    by_dataset = pd.read_csv(tmp_path / "audit" / "all_available_strategy_edge_by_dataset.csv")

    assert first["proxy_datasets_analyzed"] == 1
    assert second["proxy_datasets_analyzed"] == 1
    assert by_dataset["dataset_fingerprint"].nunique() >= 2


def test_batch_outputs_do_not_overwrite_previous_results(tmp_path: Path) -> None:
    _market(tmp_path / "nifty_1.csv", "NIFTY")
    _market(tmp_path / "banknifty_1.csv", "BANKNIFTY")
    catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "audit")

    analyzer.analyze_catalog(
        catalog_path=tmp_path / "audit" / "available_data_catalog.csv",
        out_dir=tmp_path / "audit",
        batch_size=1,
    )
    first = pd.read_csv(tmp_path / "audit" / "all_available_strategy_edge_by_dataset.csv")
    analyzer.analyze_catalog(
        catalog_path=tmp_path / "audit" / "available_data_catalog.csv",
        out_dir=tmp_path / "audit",
        batch_size=1,
        resume=1,
    )
    second = pd.read_csv(tmp_path / "audit" / "all_available_strategy_edge_by_dataset.csv")

    assert len(second) >= len(first)
