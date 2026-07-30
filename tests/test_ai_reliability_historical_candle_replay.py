from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from core.ai_reliability_agent.historical_candle_replay import (
    _manifest_failures,
    analyze_historical_candle_partition,
    main,
    replay_historical_candles,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "ai_reliability_real_artifact"
REAL_MANIFEST = FIXTURE_ROOT / "upstox_fetch_manifest_20250521.json"


def _real_shaped_candle_file(tmp_path: Path, *, fallback: bool = False) -> Path:
    start = datetime(2025, 5, 21, 3, 45, tzinfo=timezone.utc)
    timestamps = [start + timedelta(minutes=index) for index in range(3)]
    target = tmp_path / "NIFTY_20250521.parquet"
    pq.write_table(
        pa.table({
            "timestamp": timestamps,
            "symbol": ["NIFTY"] * 3,
            "open": [24800.0, 24810.0, 24805.0],
            "high": [24815.0, 24820.0, 24812.0],
            "low": [24795.0, 24800.0, 24798.0],
            "close": [24810.0, 24805.0, 24808.0],
            "volume": [0.0, 0.0, 0.0],
            "oi": [0.0, 0.0, 0.0],
            "source": ["upstox"] * 3,
            "interval": ["1minute"] * 3,
            "fetch_timestamp": [datetime(2026, 7, 6, tzinfo=timezone.utc)] * 3,
            "fetch_start_date": ["2025-05-21"] * 3,
            "fetch_end_date": ["2025-05-21"] * 3,
            "data_origin": ["upstox_api"] * 3,
            "synthetic": [False] * 3,
            "mock": [False] * 3,
            "fallback": [fallback] * 3,
            "provider": ["upstox"] * 3,
            "source_endpoint": [
                "/v3/historical-candle/NSE_INDEX%7CNifty%2050/minutes/1/2025-05-21/2025-05-21"
            ] * 3,
        }),
        target,
    )
    return target


def _provenance_for(path: Path, output: Path) -> Path:
    from core.ai_reliability_agent.historical_replay import sha256_file

    output.write_text(json.dumps({
        "synthetic": False,
        "mock": False,
        "fallback": False,
        "files": [{
            "fixture_name": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }],
    }), encoding="utf-8")
    return output


def test_real_drive_manifest_is_certification_eligible():
    manifest = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    assert _manifest_failures(manifest) == []
    assert manifest["fetch_status"] == "UPSTOX_FETCH_SUCCEEDED_REAL_CANDLES"
    assert manifest["synthetic"] is False
    assert manifest["mock"] is False
    assert manifest["fallback"] is False
    assert manifest["certification_eligible"] is True


def test_real_shaped_upstox_candles_pass_deterministic_replay(tmp_path):
    result = analyze_historical_candle_partition(_real_shaped_candle_file(tmp_path))
    assert result["status"] == "REAL_CANDLE_REPLAY_PASS"
    assert result["parquet_profile"] == "HISTORICAL_CANDLE"
    assert result["artifact_class"] == "HISTORICAL_CANDLE_PARTITION"
    assert result["streamed_row_count"] == 3
    assert result["row_count_matches_metadata"] is True
    assert result["symbols"] == ["NIFTY"]
    assert result["intervals"] == ["1minute"]
    assert result["providers"] == ["upstox"]
    assert result["data_origins"] == ["upstox_api"]
    assert result["real_only_row_flags"] is True
    assert result["ohlc_invariant_violations"] == 0


def test_replay_accepts_manifest_and_provenance_but_not_candidate_authority(tmp_path):
    target = _real_shaped_candle_file(tmp_path)
    report = replay_historical_candles(
        target,
        fetch_manifest_path=REAL_MANIFEST,
        provenance_path=_provenance_for(target, tmp_path / "provenance.json"),
    )
    assert report["verdict"] == "REAL_HISTORICAL_CANDLE_REPLAY_PASS"
    assert report["certification_scope"] == "REAL_UPSTOX_HISTORICAL_CANDLE_COMPATIBILITY"
    assert report["real_artifact_replay_executed"] is True
    assert report["synthetic_data_used"] is False
    assert report["candidate_lifecycle_replay_eligible"] is False
    assert report["total_rows"] == 3
    assert report["manifest_failures"] == []
    assert report["provenance_failures"] == []


def test_manifest_fallback_or_ineligible_status_fails_closed():
    manifest = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
    manifest["fallback"] = True
    manifest["certification_eligible"] = False
    assert _manifest_failures(manifest) == [
        "CANDLE_MANIFEST_INVALID:fallback",
        "CANDLE_MANIFEST_INVALID:certification_eligible",
    ]


def test_row_level_fallback_is_a_hard_failure(tmp_path):
    result = analyze_historical_candle_partition(
        _real_shaped_candle_file(tmp_path, fallback=True)
    )
    assert result["status"] == "REAL_CANDLE_REPLAY_FAIL"
    assert result["fallback_true_rows"] == 3
    assert "FALLBACK_ROWS_OBSERVED" in result["hard_failures"]
    assert result["real_only_row_flags"] is False


def test_ohlc_invariant_violation_fails_closed(tmp_path):
    target = tmp_path / "bad_ohlc.parquet"
    pq.write_table(pa.table({
        "timestamp": [datetime(2025, 5, 21, tzinfo=timezone.utc)],
        "symbol": ["NIFTY"],
        "open": [100.0],
        "high": [99.0],
        "low": [98.0],
        "close": [101.0],
        "synthetic": [False],
        "mock": [False],
        "fallback": [False],
    }), target)
    result = analyze_historical_candle_partition(target)
    assert result["status"] == "REAL_CANDLE_REPLAY_FAIL"
    assert result["ohlc_invariant_violations"] == 1
    assert "OHLC_INVARIANT_VIOLATION" in result["hard_failures"]


def test_missing_row_provenance_flags_are_explicit_warning(tmp_path):
    target = tmp_path / "no_flags.parquet"
    pq.write_table(pa.table({
        "timestamp": [datetime(2025, 5, 21, tzinfo=timezone.utc)],
        "symbol": ["NIFTY"],
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
    }), target)
    result = analyze_historical_candle_partition(target)
    assert result["status"] == "REAL_CANDLE_REPLAY_PASS_WITH_WARNINGS"
    assert result["provenance_flag_missing_rows"] == 1
    assert "ROW_PROVENANCE_FLAGS_MISSING" in result["warnings"]
    assert result["real_only_row_flags"] is False


def test_duplicate_timestamp_and_cadence_gap_are_reported(tmp_path):
    start = datetime(2025, 5, 21, tzinfo=timezone.utc)
    target = tmp_path / "timing.parquet"
    pq.write_table(pa.table({
        "timestamp": [start, start, start + timedelta(minutes=3)],
        "symbol": ["NIFTY"] * 3,
        "open": [100.0] * 3, "high": [101.0] * 3,
        "low": [99.0] * 3, "close": [100.5] * 3,
        "synthetic": [False] * 3, "mock": [False] * 3, "fallback": [False] * 3,
    }), target)
    result = analyze_historical_candle_partition(target)
    assert result["duplicate_symbol_timestamp_rows"] == 1
    assert result["cadence_gap_rows"] == 1
    assert "DUPLICATE_SYMBOL_TIMESTAMPS_OBSERVED" in result["warnings"]
    assert "ONE_MINUTE_CADENCE_GAPS_OBSERVED" in result["warnings"]


def test_missing_required_candle_column_fails_closed(tmp_path):
    target = tmp_path / "missing_close.parquet"
    pq.write_table(pa.table({
        "timestamp": [datetime(2025, 5, 21, tzinfo=timezone.utc)],
        "symbol": ["NIFTY"], "open": [100.0], "high": [101.0], "low": [99.0],
    }), target)
    result = analyze_historical_candle_partition(target)
    assert result["status"] == "REAL_CANDLE_REPLAY_FAIL"
    assert result["missing_required_columns"] == ["close"]
    assert result["hard_failures"] == ["CANDLE_REQUIRED_COLUMNS_MISSING"]


def test_cli_writes_candle_replay_reports(tmp_path, capsys):
    target = _real_shaped_candle_file(tmp_path)
    output = tmp_path / "report"
    exit_code = main([
        "--input", str(target),
        "--fetch-manifest", str(REAL_MANIFEST),
        "--provenance", str(_provenance_for(target, tmp_path / "provenance.json")),
        "--output-dir", str(output),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["verdict"] == "REAL_HISTORICAL_CANDLE_REPLAY_PASS"
    assert (output / "historical_candle_real_artifact_replay.json").is_file()
    markdown = (output / "historical_candle_real_artifact_replay.md").read_text(encoding="utf-8")
    assert "REAL_UPSTOX_HISTORICAL_CANDLE_COMPATIBILITY" in markdown
    assert "Candidate-lifecycle replay eligible: `False`" in markdown


def test_nonpositive_batch_size_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="batch_size_must_be_positive"):
        analyze_historical_candle_partition(_real_shaped_candle_file(tmp_path), batch_size=0)
