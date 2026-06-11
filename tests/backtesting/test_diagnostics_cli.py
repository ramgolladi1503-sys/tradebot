from __future__ import annotations

import json
from pathlib import Path
import runpy
import sqlite3


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_main(script_path: Path):
    namespace = runpy.run_path(str(script_path))
    return namespace["main"]


def _write_runtime_sqlite(path: Path, *, rows: list[tuple[str, str]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE ticks(timestamp TEXT, symbol TEXT)")
        for row in rows or []:
            conn.execute("INSERT INTO ticks(timestamp, symbol) VALUES(?, ?)", row)
        conn.commit()


def test_diagnostics_report_is_generated(tmp_path: Path) -> None:
    _write(
        tmp_path / "data/historical/index/nifty.csv",
        "\n".join(
            [
                "timestamp,symbol,open,high,low,close,volume",
                "2018-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,10",
                "2026-01-01T09:15:00+05:30,NIFTY,1,2,0.5,1.5,12",
            ]
        ),
    )
    config_path = tmp_path / "configs/backtest.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "symbols": ["NIFTY"],
                "diagnostics_output_path": str(tmp_path / "reports/diagnostics.json"),
                "readiness_output_path": str(tmp_path / "reports/data_readiness_latest.json"),
                "catalog_output_path": str(tmp_path / "reports/catalog.json"),
                "data_roots": {
                    "UNDERLYING_INDEX_CANDLES": [str(tmp_path / "data/historical/index")],
                    "FUTURES_CANDLES": [],
                    "OPTION_CONTRACT_CANDLES_INTRADAY": [],
                    "OPTION_CONTRACT_EOD": [],
                    "OPTION_CHAIN_SNAPSHOT": [],
                    "RUNTIME_CAPTURED_LIVE_DATA": []
                }
            }
        ),
        encoding="utf-8",
    )

    diagnostics_main = _load_main(Path("scripts/backtest_data_diagnostics.py"))
    rc = diagnostics_main(["--config", str(config_path)])
    assert rc == 0
    report = json.loads((tmp_path / "reports/diagnostics.json").read_text(encoding="utf-8"))
    readiness_report = json.loads((tmp_path / "reports/data_readiness_latest.json").read_text(encoding="utf-8"))
    assert report["phase_one_verdict"] == "INCONCLUSIVE_FOR_REAL_INTRADAY_OPTIONS"
    assert readiness_report["data_readiness_verdict"] == "READY_FOR_EOD_OR_PROXY_ONLY"
    assert readiness_report["data_readiness_score"] == 35
    assert "questions" in report


def test_diagnostics_report_marks_runtime_replay_only_distinctly(tmp_path: Path) -> None:
    _write(
        tmp_path / ".runtime/logs/replay.csv",
        "\n".join(
            [
                "timestamp,symbol",
                "2026-01-01T09:15:00+05:30,NIFTY",
            ]
        ),
    )
    config_path = tmp_path / "configs/backtest.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "symbols": ["NIFTY"],
                "diagnostics_output_path": str(tmp_path / "reports/diagnostics.json"),
                "readiness_output_path": str(tmp_path / "reports/data_readiness_latest.json"),
                "catalog_output_path": str(tmp_path / "reports/catalog.json"),
                "data_roots": {
                    "UNDERLYING_INDEX_CANDLES": [],
                    "FUTURES_CANDLES": [],
                    "OPTION_CONTRACT_CANDLES_INTRADAY": [],
                    "OPTION_CONTRACT_EOD": [],
                    "OPTION_CHAIN_SNAPSHOT": [],
                    "RUNTIME_CAPTURED_LIVE_DATA": []
                },
                "runtime_replay_roots": [str(tmp_path / ".runtime/logs")]
            }
        ),
        encoding="utf-8",
    )

    diagnostics_main = _load_main(Path("scripts/backtest_data_diagnostics.py"))
    rc = diagnostics_main(["--config", str(config_path)])
    assert rc == 0
    readiness_report = json.loads((tmp_path / "reports/data_readiness_latest.json").read_text(encoding="utf-8"))
    assert readiness_report["phase_one_verdict"] == "NEED_USER_HISTORICAL_DATA"
    assert readiness_report["data_readiness_verdict"] == "READY_FOR_RUNTIME_REPLAY_ONLY"
    assert readiness_report["data_readiness_score"] == 20


def test_diagnostics_catalog_and_readiness_agree_when_runtime_source_is_empty(tmp_path: Path) -> None:
    _write_runtime_sqlite(tmp_path / ".runtime/db/DEFAULT.sqlite")
    _write(
        tmp_path / ".runtime/logs/premarket_plan.csv",
        "\n".join(
            [
                "symbol,close",
                "NIFTY,23000",
            ]
        ),
    )
    config_path = tmp_path / "configs/backtest.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "symbols": ["NIFTY"],
                "diagnostics_output_path": str(tmp_path / "reports/diagnostics.json"),
                "readiness_output_path": str(tmp_path / "reports/data_readiness_latest.json"),
                "catalog_output_path": str(tmp_path / "reports/catalog.json"),
                "data_roots": {
                    "UNDERLYING_INDEX_CANDLES": [],
                    "FUTURES_CANDLES": [],
                    "OPTION_CONTRACT_CANDLES_INTRADAY": [],
                    "OPTION_CONTRACT_EOD": [],
                    "OPTION_CHAIN_SNAPSHOT": [],
                    "RUNTIME_CAPTURED_LIVE_DATA": []
                },
                "runtime_replay_roots": [
                    str(tmp_path / ".runtime/db"),
                    str(tmp_path / ".runtime/logs"),
                ]
            }
        ),
        encoding="utf-8",
    )

    diagnostics_main = _load_main(Path("scripts/backtest_data_diagnostics.py"))
    import_main = _load_main(Path("scripts/import_historical_data.py"))

    assert diagnostics_main(["--config", str(config_path)]) == 0
    assert import_main(["--config", str(config_path), "--dry-run"]) == 0

    diagnostics_report = json.loads((tmp_path / "reports/diagnostics.json").read_text(encoding="utf-8"))
    readiness_report = json.loads((tmp_path / "reports/data_readiness_latest.json").read_text(encoding="utf-8"))
    catalog_report = json.loads((tmp_path / "reports/catalog.json").read_text(encoding="utf-8"))

    assert diagnostics_report["data_readiness_verdict"] == "NEED_USER_HISTORICAL_DATA"
    assert diagnostics_report["data_readiness_score"] == 0
    assert diagnostics_report["available_modes"] == []
    assert readiness_report["data_readiness_verdict"] == diagnostics_report["data_readiness_verdict"]
    assert readiness_report["data_readiness_score"] == diagnostics_report["data_readiness_score"]
    assert readiness_report["available_modes"] == diagnostics_report["available_modes"]
    assert catalog_report["data_readiness_verdict"] == diagnostics_report["data_readiness_verdict"]
    assert catalog_report["data_readiness_score"] == diagnostics_report["data_readiness_score"]
    live_mode = next(item for item in catalog_report["mode_feasibility"] if item["mode"] == "LIVE_CAPTURE_REPLAY")
    assert live_mode["feasible"] is False
    assert "no_replay_rows" in live_mode["reasons"]


def test_import_catalog_manifest_is_generated(tmp_path: Path) -> None:
    _write(
        tmp_path / "data/historical/options_eod/nifty.csv",
        "\n".join(
            [
                "date,underlying,expiry,strike,option_type,open,high,low,close,volume,oi",
                "2026-01-01,NIFTY,2026-01-29,23000,CE,10,12,9,11,100,1000",
            ]
        ),
    )
    config_path = tmp_path / "configs/backtest.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "symbols": ["NIFTY"],
                "catalog_output_path": str(tmp_path / "reports/catalog.json"),
                "data_roots": {
                    "UNDERLYING_INDEX_CANDLES": [],
                    "FUTURES_CANDLES": [],
                    "OPTION_CONTRACT_CANDLES_INTRADAY": [],
                    "OPTION_CONTRACT_EOD": [str(tmp_path / "data/historical/options_eod")],
                    "OPTION_CHAIN_SNAPSHOT": [],
                    "RUNTIME_CAPTURED_LIVE_DATA": []
                }
            }
        ),
        encoding="utf-8",
    )

    import_main = _load_main(Path("scripts/import_historical_data.py"))
    rc = import_main(["--config", str(config_path), "--dry-run"])
    assert rc == 0
    payload = json.loads((tmp_path / "reports/catalog.json").read_text(encoding="utf-8"))
    assert payload["source_count"] == 1


def test_phase_one_files_do_not_import_broker_or_broker_api_clients() -> None:
    phase_one_sources = [
        Path("core/backtesting/models.py"),
        Path("core/backtesting/data_loader.py"),
        Path("core/backtesting/data_catalog.py"),
        Path("scripts/backtest_data_diagnostics.py"),
        Path("scripts/import_historical_data.py"),
    ]
    forbidden_tokens = (
        "import kiteconnect",
        "from kiteconnect",
        "import requests",
        "from requests",
        "from core.broker",
        "import core.broker",
    )

    for path in phase_one_sources:
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"forbidden import token {token!r} found in {path}"
