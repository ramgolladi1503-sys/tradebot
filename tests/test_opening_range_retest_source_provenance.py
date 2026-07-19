from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

from research.opening_range_retest_source_provenance import audit


def _write_session(
    path: Path,
    *,
    symbol: str,
    rows: int = 375,
    start: str = "2026-07-06T09:15:00+05:30",
    drop_column: str | None = None,
    cadence_gap: bool = False,
    timestamps: object | None = None,
) -> None:
    start_ts = pd.Timestamp(start)
    timestamps = timestamps if timestamps is not None else pd.date_range(start=start_ts, periods=rows, freq="min")
    if cadence_gap and rows > 5:
        timestamps = timestamps.to_series().reset_index(drop=True)
        timestamps.iloc[5] = timestamps.iloc[5] + pd.Timedelta(minutes=1)
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "symbol": [symbol] * rows,
            "open": [100.0] * rows,
            "high": [101.0] * rows,
            "low": [99.0] * rows,
            "close": [100.5] * rows,
            "volume": [0.0] * rows,
        }
    )
    if drop_column:
        frame = frame.drop(columns=[drop_column])
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


def _inventory_row(path: Path, logical_path: str, symbol_value: str, *, data_role: str = "UNDERLYING_CANDLES") -> dict[str, object]:
    return {"symbol_values": [symbol_value], "data_role": data_role, **_record(path, logical_path, symbol=audit.normalize_symbol(symbol_value) or "NIFTY")}


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


def test_alternative_metadata_without_file_is_not_correct_source(tmp_path: Path, monkeypatch) -> None:
    wrong = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    missing = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    _write_session(wrong, symbol="NSE_INDEX|Nifty Bank")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    wrong_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    missing_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    wrong_record = _record(wrong, wrong_logical, symbol="NIFTY")
    rows, _ = audit.audit_records(
        {"records": [wrong_record]},
        {
            wrong_logical: {"symbol_values": ["NSE_INDEX|Nifty Bank"], "data_role": "UNDERLYING_CANDLES", **wrong_record},
            missing_logical: {
                "absolute_path": str(missing),
                "logical_path": missing_logical,
                "symbol_values": ["NSE_INDEX|Nifty 50"],
                "data_role": "UNDERLYING_CANDLES",
                "sha256": "0" * 64,
                "row_count": 375,
                "byte_size": 1,
            },
        },
    )
    classes = rows[0]["classifications"]
    assert "ALTERNATIVE_FILE_MISSING" in classes
    assert "CORRECT_ALTERNATIVE_SOURCE_FOUND" not in classes
    assert "CORRECT_SOURCE_MISSING" in classes


def test_alternative_verification_rejects_hash_size_row_schema_session_symbol_and_history(tmp_path: Path, monkeypatch) -> None:
    wrong = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    _write_session(wrong, symbol="NSE_INDEX|Nifty Bank")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    wrong_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    wrong_record = _record(wrong, wrong_logical, symbol="NIFTY")
    inventory = {wrong_logical: {"symbol_values": ["NSE_INDEX|Nifty Bank"], "data_role": "UNDERLYING_CANDLES", **wrong_record}}
    cases = [
        ("hash", {"sha256": "0" * 64}, "ALTERNATIVE_HASH_MISMATCH"),
        ("size", {"byte_size": 1}, "ALTERNATIVE_SIZE_MISMATCH"),
        ("row", {"row_count": 1}, "ALTERNATIVE_ROW_COUNT_MISMATCH"),
        ("schema", {"drop_column": "volume"}, "ALTERNATIVE_SCHEMA_INVALID"),
        ("session", {"start": "2026-07-07T09:15:00+05:30"}, "ALTERNATIVE_SESSION_INVALID"),
        ("symbol", {"symbol": "SENSEX"}, "ALTERNATIVE_SYMBOL_INVALID"),
        ("history", {"cadence_gap": True}, "ALTERNATIVE_HISTORY_INVALID"),
    ]
    for label, override, expected_class in cases:
        right = tmp_path / f"runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_{label}_20260706.parquet"
        _write_session(
            right,
            symbol=str(override.get("symbol", "NSE_INDEX|Nifty 50")),
            start=str(override.get("start", "2026-07-06T09:15:00+05:30")),
            drop_column=override.get("drop_column"),
            cadence_gap=bool(override.get("cadence_gap", False)),
        )
        logical = f"runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_{label}_20260706.parquet"
        row = _inventory_row(right, logical, "NSE_INDEX|Nifty 50")
        row.update({key: value for key, value in override.items() if key in {"sha256", "byte_size", "row_count"}})
        rows, _ = audit.audit_records({"records": [wrong_record]}, {**inventory, logical: row})
        assert expected_class in rows[0]["classifications"]
        assert "CORRECT_ALTERNATIVE_SOURCE_FOUND" not in rows[0]["classifications"]


def test_two_verified_alternatives_are_ambiguous(tmp_path: Path, monkeypatch) -> None:
    wrong = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    alt_a = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    alt_b = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    _write_session(wrong, symbol="NSE_INDEX|Nifty Bank")
    _write_session(alt_a, symbol="NIFTY")
    _write_session(alt_b, symbol="NSE_INDEX|Nifty 50")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    wrong_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    alt_a_logical = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    alt_b_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_20260706.parquet"
    wrong_record = _record(wrong, wrong_logical, symbol="NIFTY")
    rows, _ = audit.audit_records(
        {"records": [wrong_record]},
        {
            wrong_logical: {"symbol_values": ["NSE_INDEX|Nifty Bank"], "data_role": "UNDERLYING_CANDLES", **wrong_record},
            alt_a_logical: _inventory_row(alt_a, alt_a_logical, "NIFTY"),
            alt_b_logical: _inventory_row(alt_b, alt_b_logical, "NSE_INDEX|Nifty 50"),
        },
    )
    assert "AMBIGUOUS_ALTERNATIVE_SOURCES" in rows[0]["classifications"]


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


def test_duplicate_identity_audit_distinguishes_duplicate_cases(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    a = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet"
    b = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_DUP_20260706.parquet"
    _write_session(a, symbol="NIFTY")
    _write_session(b, symbol="NIFTY")
    record_a = _record(a, "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_20260706.parquet")
    record_b = _record(b, "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_DUP_20260706.parquet")
    same_logical = {**record_b, "logical_path": record_a["logical_path"]}
    same_physical_cross_symbol = {**record_a, "symbol": "BANKNIFTY"}
    same_sha_cross_symbol = {**record_b, "symbol": "BANKNIFTY", "sha256": record_a["sha256"]}
    rows, _ = audit.audit_records(
        {"records": [record_a, record_b, same_logical, same_physical_cross_symbol, same_sha_cross_symbol]},
        {},
    )
    groups = audit.duplicate_identity_groups(
        [record_a, record_b, same_logical, same_physical_cross_symbol, same_sha_cross_symbol],
        {},
        rows,
    )
    assert groups["declared"]["declared_duplicate_session_symbol_assignment"]
    assert groups["declared"]["declared_duplicate_logical_path"]
    assert groups["declared"]["declared_duplicate_resolved_path"]
    assert groups["declared"]["declared_duplicate_sha"]
    assert groups["observed"]["observed_duplicate_resolved_path"]
    assert groups["observed"]["observed_duplicate_actual_sha"]
    assert groups["observed"]["observed_cross_symbol_physical_file_reuse"]
    assert groups["observed"]["observed_cross_symbol_actual_sha_reuse"]


def test_observed_duplicate_sha_uses_actual_bytes_not_declared_sha(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    a = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_A_20260706.parquet"
    b = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_B_20260706.parquet"
    _write_session(a, symbol="NIFTY")
    b.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a, b)
    logical_a = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_A_20260706.parquet"
    logical_b = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_B_20260706.parquet"
    record_a = _record(a, logical_a)
    record_b = {**_record(b, logical_b), "sha256": "1" * 64}
    rows, _ = audit.audit_records({"records": [record_a, record_b]}, {logical_a: {"symbol_values": ["NIFTY"], **record_a}, logical_b: {"symbol_values": ["NIFTY"], **record_b}})
    groups = audit.duplicate_identity_groups([record_a, record_b], {}, rows)
    assert not groups["declared"]["declared_duplicate_sha"]
    assert groups["observed"]["observed_duplicate_actual_sha"]


def test_declared_sha_duplicate_does_not_prove_actual_byte_duplicate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    a = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_A_20260706.parquet"
    b = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_B_20260706.parquet"
    _write_session(a, symbol="NIFTY")
    _write_session(b, symbol="NIFTY", start="2026-07-06T09:16:00+05:30")
    logical_a = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_A_20260706.parquet"
    logical_b = "runtime/upstox_candidate_replay/20260706/underlying/NIFTY_B_20260706.parquet"
    record_a = _record(a, logical_a)
    record_b = {**_record(b, logical_b), "sha256": record_a["sha256"]}
    rows, _ = audit.audit_records({"records": [record_a, record_b]}, {logical_a: {"symbol_values": ["NIFTY"], **record_a}, logical_b: {"symbol_values": ["NIFTY"], **record_b}})
    groups = audit.duplicate_identity_groups([record_a, record_b], {}, rows)
    assert groups["declared"]["declared_duplicate_sha"]
    assert not groups["observed"]["observed_duplicate_actual_sha"]


def test_root_cause_is_derived_without_hard_coded_date(tmp_path: Path, monkeypatch) -> None:
    wrong = tmp_path / "runtime/upstox_candidate_replay/20260711/underlying/NSE_INDEX|Nifty Bank_20260711.parquet"
    right = tmp_path / "runtime/upstox_candidate_replay/20260711/underlying/NSE_INDEX|Nifty 50_20260711.parquet"
    _write_session(wrong, symbol="NSE_INDEX|Nifty Bank", start="2026-07-11T09:15:00+05:30")
    _write_session(right, symbol="NSE_INDEX|Nifty 50", start="2026-07-11T09:15:00+05:30")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    wrong_logical = "runtime/upstox_candidate_replay/20260711/underlying/NSE_INDEX|Nifty Bank_20260711.parquet"
    right_logical = "runtime/upstox_candidate_replay/20260711/underlying/NSE_INDEX|Nifty 50_20260711.parquet"
    wrong_record = _record(wrong, wrong_logical, symbol="NIFTY")
    wrong_record["session_date"] = "2026-07-11"
    right_row = _inventory_row(right, right_logical, "NSE_INDEX|Nifty 50")
    right_row["session_date"] = "2026-07-11"
    rows, _ = audit.audit_records(
        {"records": [wrong_record]},
        {wrong_logical: {"symbol_values": ["NSE_INDEX|Nifty Bank"], "data_role": "UNDERLYING_CANDLES", **wrong_record}, right_logical: right_row},
    )
    causes = audit.derive_root_causes(rows)
    assert "2026-07-11" in causes
    assert causes["2026-07-11"]["causal_root_cause"] == "SELECTOR_SYMBOL_NORMALIZATION_MISCLASSIFIED_BANKNIFTY_AS_NIFTY"
    assert "DUPLICATE_NIFTY_SESSION_ASSIGNMENT" in causes["2026-07-11"]["causal_consequences"]
    assert "MANIFEST_PATH_MISMATCH" in causes["2026-07-11"]["observed_consistency_findings"]
    assert "WRONG_INVENTORY_SYMBOL" not in json.dumps(causes["2026-07-11"])


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
    assert "SOURCE_HISTORY_INVALID" in rows[0]["classifications"]


def test_source_root_containment_rejects_external_absolute_and_traversal_before_probe(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    outside = tmp_path / "outside.parquet"
    _write_session(outside, symbol="NIFTY")
    cases = [
        {"logical_path": "../outside.parquet", "absolute_path": str(outside)},
        {"logical_path": "runtime/upstox_candidate_replay/20260706/underlying/missing.parquet", "absolute_path": str(outside)},
        {"logical_path": str(outside), "absolute_path": str(outside)},
    ]
    for case in cases:
        record = {
            **case,
            "symbol": "NIFTY",
            "session_date": "2026-07-06",
            "sha256": "0" * 64,
            "row_count": 375,
            "byte_size": 1,
        }
        rows, _ = audit.audit_records({"records": [record]}, {})
        assert "SOURCE_OUTSIDE_ALLOWED_ROOT" in rows[0]["classifications"]
        assert rows[0]["source_probe"]["sha256"] is None


def test_source_root_containment_rejects_symlink_escape(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    outside = tmp_path / "outside/source.parquet"
    _write_session(outside, symbol="NIFTY")
    link = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/LINK_20260706.parquet"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    logical = "runtime/upstox_candidate_replay/20260706/underlying/LINK_20260706.parquet"
    record = {"logical_path": logical, "absolute_path": str(link), "symbol": "NIFTY", "session_date": "2026-07-06", "sha256": "0" * 64, "row_count": 375, "byte_size": 1}
    rows, _ = audit.audit_records({"records": [record]}, {})
    assert "SOURCE_OUTSIDE_ALLOWED_ROOT" in rows[0]["classifications"]
    assert rows[0]["source_probe"]["sha256"] is None


def test_alternative_full_session_contract_rejects_inventory_matched_incomplete_and_wrong_bounds(tmp_path: Path, monkeypatch) -> None:
    wrong = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    _write_session(wrong, symbol="NSE_INDEX|Nifty Bank")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    wrong_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    wrong_record = _record(wrong, wrong_logical, symbol="NIFTY")
    cases = [
        ("short", {"rows": 374, "row_count": 374}, "ALTERNATIVE_INCOMPLETE_SESSION"),
        ("shifted", {"start": "2026-07-06T09:16:00+05:30"}, "ALTERNATIVE_WRONG_SESSION_BOUNDS"),
    ]
    for label, kwargs, expected in cases:
        right = tmp_path / f"runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_{label}_20260706.parquet"
        _write_session(right, symbol="NSE_INDEX|Nifty 50", rows=int(kwargs.get("rows", 375)), start=str(kwargs.get("start", "2026-07-06T09:15:00+05:30")))
        logical = f"runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_{label}_20260706.parquet"
        row = _inventory_row(right, logical, "NSE_INDEX|Nifty 50")
        if "row_count" in kwargs:
            row["row_count"] = kwargs["row_count"]
        rows, _ = audit.audit_records({"records": [wrong_record]}, {wrong_logical: {"symbol_values": ["NSE_INDEX|Nifty Bank"], "data_role": "UNDERLYING_CANDLES", **wrong_record}, logical: row})
        assert expected in rows[0]["classifications"]
        assert "CORRECT_ALTERNATIVE_SOURCE_FOUND" not in rows[0]["classifications"]


def test_alternative_full_session_contract_rejects_duplicate_and_missing_extra_minute(tmp_path: Path, monkeypatch) -> None:
    wrong = tmp_path / "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    _write_session(wrong, symbol="NSE_INDEX|Nifty Bank")
    monkeypatch.setattr(audit, "PROJECT_ROOT", tmp_path)
    wrong_logical = "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"
    wrong_record = _record(wrong, wrong_logical, symbol="NIFTY")
    base = pd.date_range(start=pd.Timestamp("2026-07-06T09:15:00+05:30"), periods=375, freq="min").to_series().reset_index(drop=True)
    cases = [
        ("duplicate", base.mask(base.index == 5, base.iloc[4])),
        ("missing_extra", base.mask(base.index == 5, base.iloc[5] + pd.Timedelta(minutes=1))),
    ]
    for label, timestamps in cases:
        right = tmp_path / f"runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_{label}_20260706.parquet"
        _write_session(right, symbol="NSE_INDEX|Nifty 50", timestamps=timestamps)
        logical = f"runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty 50_{label}_20260706.parquet"
        row = _inventory_row(right, logical, "NSE_INDEX|Nifty 50")
        rows, _ = audit.audit_records({"records": [wrong_record]}, {wrong_logical: {"symbol_values": ["NSE_INDEX|Nifty Bank"], "data_role": "UNDERLYING_CANDLES", **wrong_record}, logical: row})
        assert "ALTERNATIVE_HISTORY_INVALID" in rows[0]["classifications"]
        assert "CORRECT_ALTERNATIVE_SOURCE_FOUND" not in rows[0]["classifications"]


def test_blast_radius_separates_exact_emissions_from_upper_bound() -> None:
    ledger = {
        "records": [
            {"session_date": "2026-07-06", "symbol": "NIFTY", "setup_id": "a", "direction": "BUY_CALL"},
            {"session_date": "2026-07-06", "symbol": "NIFTY", "setup_id": "b", "direction": "BUY_PUT"},
            {"session_date": "2026-07-06", "symbol": "SENSEX", "setup_id": "c", "direction": "BUY_CALL"},
        ]
    }
    summary = {"file_profiles": [{"path": "/x/runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet", "emission_count": 1}]}
    mislabeled = [{"logical_path": "runtime/upstox_candidate_replay/20260706/underlying/NSE_INDEX|Nifty Bank_20260706.parquet"}]
    blast = audit.candidate_blast_radius(ledger, summary, {("2026-07-06", "NIFTY")}, mislabeled)
    assert blast["exact_wrong_source_emission_count"] == 1
    assert blast["exact_affected_candidate_ids_available"] is False
    assert blast["exact_affected_candidate_ids"] == []
    assert blast["session_symbol_candidate_upper_bound_count"] == 2
    assert blast["session_symbol_candidate_upper_bound_directions"] == {"BUY_CALL": 1, "BUY_PUT": 1}
    assert blast["unaffected_subset_semantic_hash"] == audit.candidate_blast_radius(ledger, summary, {("2026-07-06", "NIFTY")}, mislabeled)["unaffected_subset_semantic_hash"]


def test_evidence_contract_fields_are_machine_detectable(tmp_path: Path) -> None:
    payload = {
        "mode": "RESEARCH_ORB_PHASE1_SOURCE_PROVENANCE_AUDIT",
        "candidate_id": "opening_range_retest_source_provenance_audit_v1",
        "decision": "ORB_PHASE1_INVALID",
        "reason": "test reason",
        "timestamp": "2026-07-18T00:00:00+00:00",
        "is_order_action": False,
        "broker_api_called": False,
        "source": "docs/agent_reviews/opening_range_retest_source_provenance_audit_v1.json",
        "classification_counts": {},
        "defective_source_record_count": 0,
        "mislabeled_source_record_count": 0,
        "duplicate_contaminated_source_record_count": 0,
        "affected_session_symbol_keys": [],
        "records_audited": 0,
        "causal_root_cause_count": 0,
        "causal_root_cause_by_date": {},
        "source_root_containment_failures": 0,
        "alternative_session_contract_failures": 0,
        "duplicate_identity_audit": {
            "declared_duplicate_identity_counts": {},
            "observed_duplicate_identity_counts": {},
            "groups": {"declared": {}, "observed": {}},
        },
        "observed_invariants": {"selected_source_count": 0, "recomputed_manifest_semantic_hash": "", "candidate_count": 0, "candidate_semantic_hash": ""},
        "candidate_blast_radius": {
            "exact_wrong_source_emission_count": 0,
            "session_symbol_candidate_upper_bound_count": 0,
            "exact_affected_candidate_ids_available": False,
            "unaffected_candidate_count": 0,
            "unaffected_subset_semantic_hash": "",
        },
    }
    digest = audit.write_outputs(payload, json_path=tmp_path / "audit.json", md_path=tmp_path / "audit.md")
    loaded = json.loads((tmp_path / "audit.json").read_text())
    assert digest == (tmp_path / "audit.json.sha256").read_text().split()[0]
    for field in ("mode", "candidate_id", "decision", "reason", "timestamp", "is_order_action", "broker_api_called", "source"):
        assert field in loaded
        assert f"- {field}:" in (tmp_path / "audit.md").read_text()
