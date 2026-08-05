from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_psilor_drive_corpus.py"
spec = importlib.util.spec_from_file_location("audit_psilor_drive_corpus", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def session(checksums):
    return {"checksums": checksums, "total_files": len(checksums), "total_bytes": 100}


def chunk(seq=1, digest="a" * 64, path="normalized/a.parquet", rows=1, size=1):
    return {
        "run_id": "r1",
        "partition": "asset_class=option/trade_date=2026-08-05/provider=upstox/instrument_family=NIFTY/hour=07",
        "chunk_sequence": seq,
        "relative_path": path,
        "row_count": rows,
        "size_bytes": size,
        "sha256": digest,
        "first_source_timestamp": 1,
        "last_source_timestamp": 2,
    }


def test_manifest_integrity_passes_clean_data():
    item = chunk()
    integrity, detail = mod.audit_manifests(
        session({item["relative_path"]: item["sha256"]}), [item]
    )
    assert integrity.missing_from_sealed_manifest == 0
    assert integrity.hash_mismatches == 0
    assert integrity.chunk_sequence_anomaly_groups == 0
    assert detail["asset_inventory"]["option:NIFTY"]["rows"] == 1


def test_manifest_rejects_missing_sealed_hash():
    item = chunk()
    integrity, _ = mod.audit_manifests(session({}), [item])
    assert integrity.missing_from_sealed_manifest == 1


def test_manifest_detects_sequence_gap():
    first = chunk(seq=1, path="normalized/1.parquet", digest="1" * 64)
    third = chunk(seq=3, path="normalized/3.parquet", digest="3" * 64)
    sealed = {
        first["relative_path"]: first["sha256"],
        third["relative_path"]: third["sha256"],
    }
    integrity, detail = mod.audit_manifests(session(sealed), [first, third])
    assert integrity.chunk_sequence_anomaly_groups == 1
    assert detail["chunk_sequence_anomalies"][0]["missing"] == [2]


def test_sequence_equality_is_separate_from_backward_regression():
    summary = mod.summarize_sequence_issues(
        [
            "Non-monotonic local sequence 10 -> 10 in a.parquet",
            "Non-monotonic local sequence 11 -> 10 in b.parquet",
        ]
    )
    assert summary.equal == 1
    assert summary.backward == 1
    assert summary.affected_files == 2


def test_classification_requires_tie_audit_for_equality_only():
    item = chunk()
    source = session({item["relative_path"]: item["sha256"]})
    integrity, _ = mod.audit_manifests(source, [item])
    sequence = mod.summarize_sequence_issues(
        ["Non-monotonic local sequence 10 -> 10 in a.parquet"]
    )
    result = mod.classify(
        source,
        {"raw_valid": True, "normalized_valid": False},
        {"status": "PASS", "errors": []},
        integrity,
        sequence,
    )
    assert (
        result["normalized_reuse_verdict"]
        == "NORMALIZED_REUSE_REQUIRES_EQUAL_SEQUENCE_TIE_AUDIT"
    )
    assert result["data_ready_for_dorl_only"] is False


def test_classification_rebuilds_on_backward_regression():
    item = chunk()
    source = session({item["relative_path"]: item["sha256"]})
    integrity, _ = mod.audit_manifests(source, [item])
    sequence = mod.summarize_sequence_issues(
        ["Non-monotonic local sequence 11 -> 10 in a.parquet"]
    )
    result = mod.classify(
        source,
        {"raw_valid": True, "normalized_valid": False},
        {"status": "PASS", "errors": []},
        integrity,
        sequence,
    )
    assert result["normalized_reuse_verdict"] == "REBUILD_FROM_RAW_REQUIRED"


def test_embedded_schema_detects_bid_and_ask(tmp_path):
    metadata = {
        "index_columns": [],
        "columns": [
            {"name": "bid_price", "pandas_type": "float64", "numpy_type": "float64"},
            {"name": "ask_price", "pandas_type": "float64", "numpy_type": "float64"},
        ],
        "pandas_version": "2.2.2",
    }
    path = tmp_path / "sample.parquet"
    path.write_bytes(b"PAR1" + json.dumps(metadata).encode() + b"PAR1")
    result = mod.extract_pandas_schema(path)
    assert result["quote_schema"] == "BID_ASK_COLUMNS_PRESENT_VALUES_NOT_AUDITED"
