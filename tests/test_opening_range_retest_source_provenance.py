from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from research.opening_range_retest_source_provenance import audit


def _write_session(path: Path, *, symbol: str, rows: int = 375) -> None:
    start = pd.Timestamp("2026-07-06T09:15:00+05:30")
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range(start=start, periods=rows, freq="min"),
            "symbol": [symbol] * rows,
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.5] * rows,
            "volume": [0.0] * rows,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def _record(path: Path, logical_path: str, symbol: str = "NIFTY") -> dict[str, object]:
    return {
        "absolute_path": str(path),
        "logical_path": logical_path,
        "symbol": symbol,
        "session_date": "2026-07-06",
        "source_root": str(path.parents[2]),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count": 375,
        "byte_size": path.stat().st_size,
        "projected_columns": list(audit.EXPECTED_COLUMNS),
        "selected_via": "inventory_verified_repo_relative",
    }


def test_symbol_from_path_normalizes_index_names() -> None:
    assert audit.symbol_from_path("runtime/x/NSE_INDEX|Nifty 50_20260706.parquet") == "NIFTY"
    assert audit.symbol_from_path("runtime/x/NSE_INDEX|Nifty Bank_20260706.parquet") == "BANKNIFTY"
    assert audit.symbol_from_path("runtime/x/BSE_INDEX|SENSEX_20260706.parquet") == "SENSEX"


def test_exact_match_is_clean(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    _write_session(source, symbol="NSE_INDEX|Nifty 50")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    record = _record(source, logical)
    rows, counts = audit.audit_records({"records": [record]}, {logical: {"symbol_values": ["NSE_INDEX|Nifty 50"], **record}})
    assert rows[0]["classifications"] == ["EXACT_MATCH"]
    assert counts["EXACT_MATCH"] == 1


def test_manifest_path_mismatch_finds_correct_alternative(tmp_path: Path, monkeypatch) -> None:
    wrong = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    right = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    _write_session(wrong, symbol="NSE_INDEX|Nifty Bank")
    _write_session(right, symbol="NSE_INDEX|Nifty 50")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    wrong_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    right_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    wrong_record = _record(wrong, wrong_logical, symbol="NIFTY")
    right_record = _record(right, right_logical, symbol="NIFTY")
    rows, counts = audit.audit_records(
        {"records": [wrong_record]},
        {
            wrong_logical: {"symbol_values": ["NSE_INDEX|Nifty Bank"], "data_role": "UNDERLYING_CANDLES", **wrong_record},
            right_logical: {"symbol_values": ["NSE_INDEX|Nifty 50"], "data_role": "UNDERLYING_CANDLES", **right_record},
        },
    )
    classes = rows[0]["classifications"]
    assert "MANIFEST_PATH_MISMATCH" in classes
    assert "INVENTORY_SYMBOL_MISMATCH" in classes
    assert "SOURCE_CONTENT_SYMBOL_MISMATCH" in classes
    assert "CORRECT_ALTERNATIVE_SOURCE_FOUND" in classes
    assert counts["MANIFEST_PATH_MISMATCH"] == 1


def test_duplicate_source_assignment_is_reported(tmp_path: Path, monkeypatch) -> None:
    a = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    b = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    _write_session(a, symbol="NIFTY")
    _write_session(b, symbol="NSE_INDEX|Nifty 50")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    record_a = _record(a, "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet")
    record_b = _record(b, "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet")
    _, counts = audit.audit_records(
        {"records": [record_a, record_b]},
        {str(record_a["logical_path"]): {"symbol_values": ["NIFTY"], **record_a}, str(record_b["logical_path"]): {"symbol_values": ["NSE_INDEX|Nifty 50"], **record_b}},
    )
    assert counts["DUPLICATE_SOURCE_ASSIGNMENT"] == 2


def test_manifest_semantic_hash_is_order_stable() -> None:
    records = [
        {"symbol": "NIFTY", "session_date": "2026-07-06", "logical_path": "b", "sha256": "2"},
        {"symbol": "BANKNIFTY", "session_date": "2026-07-05", "logical_path": "a", "sha256": "1"},
    ]
    assert audit.manifest_semantic_hash(records) == audit.manifest_semantic_hash(list(reversed(records)))


def test_row_count_mismatch_is_reported(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    _write_session(source, symbol="NIFTY", rows=374)
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    logical = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    record = _record(source, logical)
    record["row_count"] = 375
    rows, _ = audit.audit_records({"records": [record]}, {logical: {"symbol_values": ["NIFTY"], **record}})
    assert "SOURCE_ROW_COUNT_MISMATCH" in rows[0]["classifications"]
    assert "SOURCE_HISTORY_INVALID" not in rows[0]["classifications"]
