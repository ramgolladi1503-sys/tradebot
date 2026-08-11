from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from core.ai_reliability_agent.historical_replay import (
    HistoricalReplayError,
    analyze_parquet_partition,
    main,
    replay_historical_market_data,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "ai_reliability_real_artifact"
REAL_FIXTURE = "ticks_1784023500.parquet"


def _decode_real_fixture(tmp_path: Path) -> Path:
    parts = sorted(FIXTURE_ROOT.glob(f"{REAL_FIXTURE}.b64.part*"))
    assert tuple(path.name for path in parts) == tuple(
        f"{REAL_FIXTURE}.b64.part{index:03d}" for index in range(1, 13)
    )
    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in parts)
    target = tmp_path / REAL_FIXTURE
    target.write_bytes(base64.b64decode(encoded, validate=True))
    provenance = json.loads((FIXTURE_ROOT / "provenance.json").read_text(encoding="utf-8"))
    expected = next(item for item in provenance["files"] if item["fixture_name"] == REAL_FIXTURE)
    observed_sha = hashlib.sha256(target.read_bytes()).hexdigest()
    assert observed_sha == expected["sha256"]
    assert target.stat().st_size == expected["size_bytes"]
    return target


def test_real_drive_partition_replays_with_exact_row_count_and_schema(tmp_path):
    target = _decode_real_fixture(tmp_path)
    result = analyze_parquet_partition(target)
    assert result["status"] == "REAL_ARTIFACT_REPLAY_PASS_WITH_WARNINGS"
    assert result["metadata_row_count"] == 2825
    assert result["streamed_row_count"] == 2825
    assert result["row_count_matches_metadata"] is True
    assert result["columns"] == [
        "ts", "instrument_key", "ltp", "bid_price", "ask_price", "delta",
        "theta", "gamma", "vega", "iv", "volume", "oi",
    ]
    assert result["parquet_magic_valid"] is True
    assert result["ltp_negative_rows"] == 0


def test_real_drive_index_partition_preserves_null_quote_semantics(tmp_path):
    result = analyze_parquet_partition(_decode_real_fixture(tmp_path))
    assert result["artifact_class"] == "INDEX_ONLY_TICK_PARTITION"
    assert result["quote_complete_rows"] == 0
    assert result["optional_null_counts"]["bid_price"] == 2825
    assert result["optional_null_counts"]["ask_price"] == 2825
    assert result["greeks_complete_rows"] == 0
    assert "INDEX_ONLY_PARTITION_NO_OPTION_ANALYTICS" in result["warnings"]
    assert result["hard_failures"] == []


def test_real_drive_fixture_timestamp_bounds_are_read_from_rows(tmp_path):
    result = analyze_parquet_partition(_decode_real_fixture(tmp_path), batch_size=257)
    assert result["timestamp_min_epoch"] == pytest.approx(1784023245.8474739, abs=1e-6)
    assert result["timestamp_max_epoch"] == pytest.approx(1784023500.277816, abs=1e-6)
    assert result["duration_seconds"] == pytest.approx(254.4303422, abs=1e-5)
    assert result["invalid_timestamp_rows"] == 0


def test_replay_preserves_real_drive_provenance_and_collector_manifest(tmp_path):
    report = replay_historical_market_data(
        _decode_real_fixture(tmp_path),
        collector_manifest_path=FIXTURE_ROOT / "collector_manifest_20260714.json",
        provenance_path=FIXTURE_ROOT / "provenance.json",
    )
    assert report["real_artifact_replay_executed"] is True
    assert report["synthetic_data_used"] is False
    assert report["file_count"] == 1
    assert report["total_rows"] == 2825
    assert report["hard_failure_file_count"] == 0
    assert report["provenance_failures"] == []
    assert report["collector_manifest"]["total_messages"] == 113465
    assert report["collector_manifest"]["dropped_messages"] == 0
    assert report["collector_manifest"]["parse_failures"] == 0
    assert report["candidate_lifecycle_replay_eligible"] is False
    assert report["certification_scope"] == "REAL_MARKET_DATA_PARQUET_COMPATIBILITY"


def test_provenance_hash_mismatch_fails_closed(tmp_path):
    target = _decode_real_fixture(tmp_path)
    provenance = json.loads((FIXTURE_ROOT / "provenance.json").read_text(encoding="utf-8"))
    provenance["files"][0]["sha256"] = "0" * 64
    path = tmp_path / "bad_provenance.json"
    path.write_text(json.dumps(provenance), encoding="utf-8")
    report = replay_historical_market_data(target, provenance_path=path)
    assert report["verdict"] == "REAL_ARTIFACT_REPLAY_FAIL"
    assert report["provenance_failures"] == [f"PROVENANCE_SHA256_MISMATCH:{REAL_FIXTURE}"]


def test_synthetic_option_rows_exercise_option_specific_quality_logic(tmp_path):
    target = tmp_path / "option_rows.parquet"
    pq.write_table(
        pa.table({
            "ts": [1.0, 2.0],
            "instrument_key": ["BSE_FO|1", "NSE_FO|2"],
            "ltp": [10.0, 11.0],
            "bid_price": [9.5, 11.5],
            "ask_price": [10.5, 11.0],
            "delta": [0.5, -0.4], "theta": [-1.0, -1.1],
            "gamma": [0.01, 0.02], "vega": [2.0, 2.1], "iv": [15.0, 16.0],
        }),
        target,
    )
    result = analyze_parquet_partition(target)
    assert result["artifact_class"] == "OPTION_CHAIN_TICK_PARTITION"
    assert result["option_row_count"] == 2
    assert result["quote_complete_rows"] == 2
    assert result["greeks_complete_rows"] == 2
    assert result["crossed_market_rows"] == 1
    assert "CROSSED_MARKET_ROWS_OBSERVED" in result["warnings"]


def test_collector_manifest_with_drops_downgrades_replay(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"dropped_messages": 3, "parse_failures": 0}), encoding="utf-8")
    report = replay_historical_market_data(_decode_real_fixture(tmp_path), collector_manifest_path=manifest)
    assert report["verdict"] == "REAL_ARTIFACT_REPLAY_PASS_WITH_WARNINGS"
    assert report["collector_manifest_warnings"] == ["COLLECTOR_DROPPED_MESSAGES_REPORTED"]


def test_invalid_manifest_count_is_rejected(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"dropped_messages": "unknown"}), encoding="utf-8")
    with pytest.raises(HistoricalReplayError, match="collector_manifest_invalid_integer"):
        replay_historical_market_data(_decode_real_fixture(tmp_path), collector_manifest_path=manifest)


def test_missing_required_column_fails_closed(tmp_path):
    target = tmp_path / "missing_ltp.parquet"
    pq.write_table(pa.table({"ts": [1.0], "instrument_key": ["NSE_INDEX|Nifty 50"]}), target)
    result = analyze_parquet_partition(target)
    assert result["status"] == "REAL_ARTIFACT_REPLAY_FAIL"
    assert result["missing_required_columns"] == ["ltp"]
    assert "REQUIRED_COLUMNS_MISSING" in result["hard_failures"]


def test_negative_ltp_fails_closed(tmp_path):
    target = tmp_path / "negative_ltp.parquet"
    pq.write_table(pa.table({"ts": [1.0], "instrument_key": ["BSE_FO|1"], "ltp": [-1.0]}), target)
    result = analyze_parquet_partition(target)
    assert result["status"] == "REAL_ARTIFACT_REPLAY_FAIL"
    assert result["ltp_negative_rows"] == 1
    assert "NEGATIVE_LTP_OBSERVED" in result["hard_failures"]


def test_timestamp_regression_is_detected(tmp_path):
    target = tmp_path / "out_of_order.parquet"
    pq.write_table(pa.table({"ts": [2.0, 1.0], "instrument_key": ["BSE_FO|1"] * 2, "ltp": [10.0, 11.0]}), target)
    result = analyze_parquet_partition(target, batch_size=1)
    assert result["timestamp_order_violations"] == 1
    assert "TIMESTAMP_ORDER_VIOLATIONS_OBSERVED" in result["warnings"]


def test_invalid_parquet_magic_fails_before_pyarrow(tmp_path):
    target = tmp_path / "broken.parquet"
    target.write_bytes(b"not-parquet")
    result = analyze_parquet_partition(target)
    assert result["status"] == "REAL_ARTIFACT_REPLAY_FAIL"
    assert result["parquet_magic_valid"] is False
    assert result["hard_failures"] == ["PARQUET_MAGIC_INVALID"]


def test_empty_directory_fails_with_explicit_limitation(tmp_path):
    report = replay_historical_market_data(tmp_path)
    assert report["verdict"] == "REAL_ARTIFACT_REPLAY_FAIL"
    assert report["file_count"] == 0
    assert report["real_artifact_replay_executed"] is False
    assert report["limitations"][0] == "No parquet artifacts were discovered at the requested input path."


def test_nonpositive_batch_size_is_rejected(tmp_path):
    with pytest.raises(HistoricalReplayError, match="batch_size_must_be_positive"):
        analyze_parquet_partition(_decode_real_fixture(tmp_path), batch_size=0)


def test_cli_writes_machine_and_human_reports(tmp_path, capsys):
    output = tmp_path / "report"
    exit_code = main([
        "--input", str(_decode_real_fixture(tmp_path)),
        "--collector-manifest", str(FIXTURE_ROOT / "collector_manifest_20260714.json"),
        "--provenance", str(FIXTURE_ROOT / "provenance.json"),
        "--output-dir", str(output),
    ])
    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["real_artifact_replay_executed"] is True
    assert (output / "historical_real_artifact_replay.json").is_file()
    markdown = (output / "historical_real_artifact_replay.md").read_text(encoding="utf-8")
    assert "REAL_MARKET_DATA_PARQUET_COMPATIBILITY" in markdown
    assert "Candidate-lifecycle replay eligible: `False`" in markdown
