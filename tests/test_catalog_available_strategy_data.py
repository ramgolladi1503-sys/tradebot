from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import catalog_available_strategy_data as catalog


def _ohlc(path: Path, *, volume: int = 0) -> Path:
    frame = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-06-29 09:15:00") + pd.Timedelta(minutes=i),
                "open": 100 + i,
                "high": 101 + i,
                "low": 99 + i,
                "close": 100.5 + i,
                "volume": volume,
                "instrument": "NIFTY",
            }
            for i in range(5)
        ]
    )
    frame.to_csv(path, index=False)
    return path


def test_zero_volume_data_invalidates_vwap_volume_proxy(tmp_path: Path) -> None:
    path = _ohlc(tmp_path / "nifty.csv", volume=0)

    result = catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "out")
    row = result[result["path"] == str(path)].iloc[0]

    assert row["detected_dataset_type"] == "INDEX_OHLC"
    assert row["volume_quality"] == "ZERO_VOLUME"
    assert bool(row["usable_for_directional_proxy"]) is True
    assert bool(row["usable_for_vwap_or_volume_proxy"]) is False


def test_generated_backtest_reports_are_not_raw_market_data(tmp_path: Path) -> None:
    report_dir = tmp_path / "runtime" / "backtests" / "x"
    report_dir.mkdir(parents=True)
    path = report_dir / "all_strategy_proxy_summary.csv"
    pd.DataFrame([{"strategy": "x", "avg_net_bps": 1.2, "verdict": "ROBUST_DIRECTIONAL_PROXY"}]).to_csv(path, index=False)

    result = catalog.build_catalog(roots=[tmp_path / "runtime"], out_dir=tmp_path / "out")
    row = result[result["path"] == str(path)].iloc[0]

    assert row["detected_dataset_type"] == "BACKTEST_REPORT"
    assert row["evidence_origin"] == "DERIVED_BACKTEST_OUTPUT"
    assert bool(row["eligible_as_raw_market_input"]) is False
    assert bool(row["usable_for_directional_proxy"]) is False


def test_duplicate_datasets_are_deduped(tmp_path: Path) -> None:
    one = _ohlc(tmp_path / "one.csv", volume=10)
    two = _ohlc(tmp_path / "two.csv", volume=10)

    result = catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "out")
    rows = result[result["detected_dataset_type"] == "INDEX_OHLC"]

    assert len(rows) >= 2
    assert rows["dataset_fingerprint"].nunique() == 1
    assert rows["duplicate_group_id"].nunique() == 1
    assert rows["canonical_dataset_path"].nunique() == 1
    assert bool(rows.loc[rows["path"] == str(one), "is_duplicate"].iloc[0]) is False
    assert bool(rows.loc[rows["path"] == str(two), "is_duplicate"].iloc[0]) is True


def test_malformed_files_are_isolated_into_catalog_rows(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    result = catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "out")
    row = result[result["path"] == str(bad)].iloc[0]

    assert row["detected_dataset_type"] == "INVALID_OR_EMPTY"
    assert "read_error" in row["reason"]


def test_option_quote_truth_requires_bid_ask_depth_for_executable_replay(tmp_path: Path) -> None:
    ltp_only = tmp_path / "option_ltp.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-06-29 09:15:00",
                "tradingsymbol": "NIFTY26JUN24000CE",
                "strike": 24000,
                "option_type": "CE",
                "ltp": 100.0,
            }
        ]
    ).to_csv(ltp_only, index=False)
    quote = tmp_path / "option_quote.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-06-29 09:15:00",
                "candidate_id": "c1",
                "tradingsymbol": "NIFTY26JUN24000CE",
                "strike": 24000,
                "option_type": "CE",
                "ltp": 100.0,
                "bid": 99.5,
                "ask": 100.5,
                "depth": "{}",
            }
        ]
    ).to_csv(quote, index=False)

    result = catalog.build_catalog(roots=[tmp_path], out_dir=tmp_path / "out")
    by_path = result.set_index("path")

    assert by_path.loc[str(ltp_only), "detected_dataset_type"] == "OPTION_OHLC_OR_LTP"
    assert bool(by_path.loc[str(ltp_only), "usable_for_executable_option_replay"]) is False
    assert by_path.loc[str(quote), "detected_dataset_type"] == "OPTION_QUOTE_TRUTH"
    assert bool(by_path.loc[str(quote), "usable_for_executable_option_replay"]) is True
