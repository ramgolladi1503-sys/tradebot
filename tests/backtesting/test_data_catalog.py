from __future__ import annotations

import json
from pathlib import Path

from core.backtesting.data_catalog import build_catalog_from_config, build_diagnostics_report, load_backtest_config
from core.backtesting.models import BacktestMode, DataReadinessVerdict, HistoricalSourceType, PhaseOneVerdict


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")


def _write_config(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_date_and_symbol_coverage_and_provenance_are_preserved(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "data/historical/index/nifty.csv",
        "timestamp,symbol,open,high,low,close,volume",
        [
            "2018-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,10",
            "2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,12",
        ],
    )
    _write_config(
        tmp_path / "configs/backtest.json",
        {
            "symbols": ["NIFTY"],
            "data_roots": {
                "UNDERLYING_INDEX_CANDLES": ["data/historical/index"],
                "FUTURES_CANDLES": [],
                "OPTION_CONTRACT_CANDLES_INTRADAY": [],
                "OPTION_CONTRACT_EOD": [],
                "OPTION_CHAIN_SNAPSHOT": [],
                "RUNTIME_CAPTURED_LIVE_DATA": []
            }
        },
    )

    config = load_backtest_config(tmp_path / "configs/backtest.json")
    catalog = build_catalog_from_config(config)

    records = catalog.by_type(HistoricalSourceType.UNDERLYING_INDEX_CANDLES)
    assert len(records) == 1
    assert records[0].provenance == "user_csv"
    assert records[0].coverage.start_date == "2018-01-01"
    assert records[0].coverage.end_date == "2026-01-01"
    assert records[0].symbols == ("NIFTY",)


def test_mode_feasibility_marks_intraday_as_inconclusive_when_missing(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "data/historical/index/nifty.csv",
        "timestamp,symbol,open,high,low,close,volume",
        [
            "2018-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,10",
            "2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,12",
        ],
    )
    _write_csv(
        tmp_path / "data/historical/options_eod/nifty_options.csv",
        "date,underlying,expiry,strike,option_type,open,high,low,close,volume,oi",
        [
            "2026-01-01,NIFTY,2026-01-29,23000,CE,10,12,9,11,100,1000",
        ],
    )
    _write_config(
        tmp_path / "configs/backtest.json",
        {
            "symbols": ["NIFTY"],
            "data_roots": {
                "UNDERLYING_INDEX_CANDLES": ["data/historical/index"],
                "FUTURES_CANDLES": [],
                "OPTION_CONTRACT_CANDLES_INTRADAY": [],
                "OPTION_CONTRACT_EOD": ["data/historical/options_eod"],
                "OPTION_CHAIN_SNAPSHOT": [],
                "RUNTIME_CAPTURED_LIVE_DATA": []
            }
        },
    )

    report = build_diagnostics_report(load_backtest_config(tmp_path / "configs/backtest.json"))

    assert report["phase_one_verdict"] == PhaseOneVerdict.INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS.value
    assert report["questions"]["do_we_have_true_intraday_option_data"] is False
    assert report["questions"]["which_backtest_modes_are_feasible"][BacktestMode.OPTIONS_EOD.value] is True


def test_missing_data_returns_need_user_historical_data(tmp_path: Path) -> None:
    _write_config(
        tmp_path / "configs/backtest.json",
        {
            "symbols": ["NIFTY"],
            "data_roots": {
                "UNDERLYING_INDEX_CANDLES": [],
                "FUTURES_CANDLES": [],
                "OPTION_CONTRACT_CANDLES_INTRADAY": [],
                "OPTION_CONTRACT_EOD": [],
                "OPTION_CHAIN_SNAPSHOT": [],
                "RUNTIME_CAPTURED_LIVE_DATA": []
            }
        },
    )
    report = build_diagnostics_report(load_backtest_config(tmp_path / "configs/backtest.json"))
    assert report["phase_one_verdict"] == PhaseOneVerdict.NEED_USER_HISTORICAL_DATA.value
    assert report["data_readiness_verdict"] == DataReadinessVerdict.NEED_USER_HISTORICAL_DATA.value
    assert report["data_readiness_score"] == 0


def test_full_eight_year_intraday_data_unlocks_true_intraday_mode(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "data/historical/index/nifty.csv",
        "timestamp,symbol,open,high,low,close,volume",
        [
            "2018-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,10",
            "2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,12",
        ],
    )
    _write_csv(
        tmp_path / "data/historical/options_intraday/nifty.csv",
        "timestamp,underlying,expiry,strike,option_type,open,high,low,close,volume,oi,bid,ask",
        [
            "2018-01-01T09:15:00+05:30,NIFTY,2018-01-25,11000,CE,10,12,9,11,100,1000,10.5,11.0",
            "2026-01-01T09:15:00+05:30,NIFTY,2026-01-29,23000,CE,10,12,9,11,100,1000,10.5,11.0",
        ],
    )
    _write_config(
        tmp_path / "configs/backtest.json",
        {
            "symbols": ["NIFTY"],
            "required_span_days": 2890,
            "data_roots": {
                "UNDERLYING_INDEX_CANDLES": ["data/historical/index"],
                "FUTURES_CANDLES": [],
                "OPTION_CONTRACT_CANDLES_INTRADAY": ["data/historical/options_intraday"],
                "OPTION_CONTRACT_EOD": [],
                "OPTION_CHAIN_SNAPSHOT": [],
                "RUNTIME_CAPTURED_LIVE_DATA": []
            }
        },
    )

    report = build_diagnostics_report(load_backtest_config(tmp_path / "configs/backtest.json"))

    assert report["phase_one_verdict"] == PhaseOneVerdict.READY_FOR_PHASE_2.value
    assert report["data_readiness_verdict"] == DataReadinessVerdict.READY_FOR_TRUE_INTRADAY_OPTIONS_BACKTEST.value
    assert report["data_readiness_score"] == 100
    assert report["questions"]["which_backtest_modes_are_feasible"][BacktestMode.TRUE_OPTIONS_INTRADAY.value] is True


def test_underlying_only_unlocks_proxy_mode_only(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "data/historical/index/nifty.csv",
        "timestamp,symbol,open,high,low,close,volume",
        [
            "2018-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,10",
            "2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,12",
        ],
    )
    _write_config(
        tmp_path / "configs/backtest.json",
        {
            "symbols": ["NIFTY"],
            "data_roots": {
                "UNDERLYING_INDEX_CANDLES": ["data/historical/index"],
                "FUTURES_CANDLES": [],
                "OPTION_CONTRACT_CANDLES_INTRADAY": [],
                "OPTION_CONTRACT_EOD": [],
                "OPTION_CHAIN_SNAPSHOT": [],
                "RUNTIME_CAPTURED_LIVE_DATA": []
            }
        },
    )

    report = build_diagnostics_report(load_backtest_config(tmp_path / "configs/backtest.json"))

    assert report["data_readiness_verdict"] == DataReadinessVerdict.READY_FOR_EOD_OR_PROXY_ONLY.value
    assert report["data_readiness_score"] == 35
    assert report["questions"]["which_backtest_modes_are_feasible"][BacktestMode.UNDERLYING_SIGNAL_WITH_OPTION_PROXY.value] is True
    assert report["questions"]["which_backtest_modes_are_feasible"][BacktestMode.TRUE_OPTIONS_INTRADAY.value] is False
    assert report["questions"]["which_backtest_modes_are_feasible"][BacktestMode.HYBRID.value] is False


def test_missing_bid_ask_reduces_readiness_score_without_blocking_intraday(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "data/historical/index/nifty.csv",
        "timestamp,symbol,open,high,low,close,volume",
        [
            "2018-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,10",
            "2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,12",
        ],
    )
    _write_csv(
        tmp_path / "data/historical/options_intraday/nifty.csv",
        "timestamp,underlying,expiry,strike,option_type,open,high,low,close,volume,oi",
        [
            "2018-01-01T09:15:00+05:30,NIFTY,2018-01-25,11000,CE,10,12,9,11,100,1000",
            "2026-01-01T09:15:00+05:30,NIFTY,2026-01-29,23000,CE,10,12,9,11,100,1000",
        ],
    )
    _write_config(
        tmp_path / "configs/backtest.json",
        {
            "symbols": ["NIFTY"],
            "required_span_days": 2890,
            "data_roots": {
                "UNDERLYING_INDEX_CANDLES": ["data/historical/index"],
                "FUTURES_CANDLES": [],
                "OPTION_CONTRACT_CANDLES_INTRADAY": ["data/historical/options_intraday"],
                "OPTION_CONTRACT_EOD": [],
                "OPTION_CHAIN_SNAPSHOT": [],
                "RUNTIME_CAPTURED_LIVE_DATA": []
            }
        },
    )

    report = build_diagnostics_report(load_backtest_config(tmp_path / "configs/backtest.json"))
    intraday_mode = next(item for item in report["mode_feasibility"] if item["mode"] == BacktestMode.TRUE_OPTIONS_INTRADAY.value)

    assert report["data_readiness_score"] == 85
    assert report["questions"]["which_backtest_modes_are_feasible"][BacktestMode.TRUE_OPTIONS_INTRADAY.value] is True
    assert "missing_bid_ask_reduces_fill_realism" in intraday_mode["reasons"]


def test_partial_date_coverage_is_reported_accurately(tmp_path: Path) -> None:
    _write_csv(
        tmp_path / "data/historical/options_intraday/nifty.csv",
        "timestamp,underlying,expiry,strike,option_type,open,high,low,close,volume,oi,bid,ask",
        [
            "2024-01-01T09:15:00+05:30,NIFTY,2024-01-25,21000,CE,10,12,9,11,100,1000,10.5,11.0",
            "2025-12-31T15:30:00+05:30,NIFTY,2026-01-29,23000,CE,10,12,9,11,100,1000,10.5,11.0",
        ],
    )
    _write_config(
        tmp_path / "configs/backtest.json",
        {
            "symbols": ["NIFTY"],
            "data_roots": {
                "UNDERLYING_INDEX_CANDLES": [],
                "FUTURES_CANDLES": [],
                "OPTION_CONTRACT_CANDLES_INTRADAY": ["data/historical/options_intraday"],
                "OPTION_CONTRACT_EOD": [],
                "OPTION_CHAIN_SNAPSHOT": [],
                "RUNTIME_CAPTURED_LIVE_DATA": []
            }
        },
    )

    report = build_diagnostics_report(load_backtest_config(tmp_path / "configs/backtest.json"))
    assert report["questions"]["what_dates_are_covered"] == {
        "start_date": "2024-01-01",
        "end_date": "2025-12-31",
    }
    assert report["available_sources"][0]["coverage"]["span_days"] == 730
