from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.nifty_futures_ingestion_validation import (
    sha256_file,
    validate_candle_artifact,
    write_public_metadata,
)


def _valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": "2026-07-10T09:15:00+05:30",
                "open": 24170.0,
                "high": 24180.0,
                "low": 24160.0,
                "close": 24175.0,
                "volume": 100.0,
                "provider": "upstox_api",
                "data_origin": "upstox_api",
                "source_endpoint": "HistoryApi.get_historical_candle_data1",
                "instrument_key": "NSE_FO|61093",
                "note": "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
            },
            {
                "timestamp": "2026-07-10T09:16:00+05:30",
                "open": 24175.0,
                "high": 24185.0,
                "low": 24170.0,
                "close": 24180.0,
                "volume": 200.0,
                "provider": "upstox_api",
                "data_origin": "upstox_api",
                "source_endpoint": "HistoryApi.get_historical_candle_data1",
                "instrument_key": "NSE_FO|61093",
                "note": "safe",
            },
        ]
    )


def test_valid_fixture_produces_metadata(tmp_path):
    artifact = tmp_path / "nifty.csv"
    _valid_frame().to_csv(artifact, index=False)
    output = tmp_path / "report.json"

    report = validate_candle_artifact(artifact, output_path=output)

    assert report.validation_status == "PASS"
    assert report.blockers == ()
    assert report.row_count == 2
    assert report.vwap_formula == "close_volume_weighted: sum(close * volume) / sum(volume)"
    assert report.vwap == (24175.0 * 100.0 + 24180.0 * 200.0) / 300.0
    assert report.sha256 == sha256_file(artifact)
    assert report.metadata_path == str(output)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["validation_status"] == "PASS"
    assert saved["sha256"] == report.sha256
    assert saved["instrument_key_redacted"] == "NSE_FO|61093"
    assert saved["vwap_formula"] == "close_volume_weighted: sum(close * volume) / sum(volume)"


def test_missing_provenance_blocks(tmp_path):
    artifact = tmp_path / "missing_provenance.csv"
    frame = _valid_frame().drop(columns=["provider", "data_origin", "source_endpoint"])
    frame.to_csv(artifact, index=False)

    report = validate_candle_artifact(artifact)

    assert report.validation_status == "BLOCKED"
    assert "MISSING_PROVENANCE" in report.blockers


def test_invalid_ohlc_blocks(tmp_path):
    artifact = tmp_path / "invalid_ohlc.csv"
    frame = _valid_frame()
    frame.loc[0, "high"] = 24150.0
    frame.to_csv(artifact, index=False)

    report = validate_candle_artifact(artifact)

    assert report.validation_status == "BLOCKED"
    assert "INVALID_OHLC" in report.blockers


def test_duplicate_timestamps_block(tmp_path):
    artifact = tmp_path / "duplicate_ts.csv"
    frame = _valid_frame()
    frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    frame.to_csv(artifact, index=False)

    report = validate_candle_artifact(artifact)

    assert report.validation_status == "BLOCKED"
    assert "DUPLICATE_TIMESTAMP" in report.blockers


def test_sha256_is_deterministic(tmp_path):
    artifact = tmp_path / "sha.csv"
    _valid_frame().to_csv(artifact, index=False)

    assert sha256_file(artifact) == sha256_file(artifact)


def test_public_report_does_not_include_raw_secret_like_values(tmp_path):
    artifact = tmp_path / "secret_like.csv"
    _valid_frame().to_csv(artifact, index=False)
    report = validate_candle_artifact(artifact)
    report_path = write_public_metadata(report, tmp_path / "public.json")

    payload = report_path.read_text(encoding="utf-8")
    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in payload
    assert "Bearer" not in payload
    parsed = json.loads(payload)
    assert parsed["validation_status"] == "PASS"
    assert parsed["artifact_path"].endswith("secret_like.csv")
