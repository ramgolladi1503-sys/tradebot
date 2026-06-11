from __future__ import annotations

import json
from pathlib import Path
import runpy


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_main(script_path: Path):
    namespace = runpy.run_path(str(script_path))
    return namespace["main"]


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
