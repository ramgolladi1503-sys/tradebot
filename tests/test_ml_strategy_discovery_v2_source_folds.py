from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.ml_strategy_discovery_v2.contracts import (
    DEVELOPMENT,
    FRESH_CONSUMED,
    FRESH_LOCKED,
    HOLDOUT_LOCKED,
    VALIDATION_CONSUMED,
    canonical_hash,
)
from research.ml_strategy_discovery_v2.data import default_registry
from research.ml_strategy_discovery_v2.folds import (
    fold_manifest_hash,
    generate_anchored_folds,
    generate_nested_folds,
)
from research.ml_strategy_discovery_v2.source import (
    SourceCertificationError,
    development_manifest_payload,
    load_and_verify_manifest,
    resolve_source_file,
    verify_manifest_sidecar,
    verify_record_file,
)

def _registry_payload() -> dict:
    return {
        "ranges": [
            {"name": DEVELOPMENT, "start": None, "end": "2025-09-05", "status": "A"},
            {"name": VALIDATION_CONSUMED, "start": "2025-09-08", "end": "2026-02-05", "status": "B"},
            {"name": HOLDOUT_LOCKED, "start": "2026-02-06", "end": "2026-07-10", "status": "C"},
            {"name": FRESH_CONSUMED, "start": "2026-07-11", "end": "2026-07-21", "status": "D"},
            {"name": FRESH_LOCKED, "start": "2026-07-22", "end": None, "status": "E"},
        ]
    }


def _candidate(threshold: float = 0.5) -> dict:
    return {
        "conditions": [{"feature": "f1", "operator": ">", "threshold": threshold}],
        "imputation_values": {"f1": 0.0},
        "rule_hash": canonical_hash({"threshold": threshold}),
    }


def _frame(sessions: int = 20, rows_per_session: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-01", periods=sessions).strftime("%Y-%m-%d")
    records = []
    for session_index, session in enumerate(dates):
        for bar in range(rows_per_session):
            f1 = float(rng.normal())
            records.append(
                {
                    "session_date": session,
                    "decision_timestamp": pd.Timestamp(session) + pd.Timedelta(minutes=bar),
                    "f1": f1,
                    "f2": float(rng.normal()),
                    "label_return_r": 0.6 if f1 > 0.5 else -0.3,
                    "trend_regime": float(session_index % 3 - 1),
                    "volatility_regime": float(session_index % 2),
                    "gap_regime": float(session_index % 2),
                    "time_regime": float(bar // max(1, rows_per_session // 3)),
                }
            )
    return pd.DataFrame.from_records(records)


def _write_manifest(tmp_path: Path, records: list[dict], policies: list[dict] | None = None) -> Path:
    path = tmp_path / "manifest.json"
    payload = {
        "source_manifest_version": "v2",
        "record_count": len(records),
        "records": records,
        "special_session_policies": policies or [],
    }
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    Path(f"{path}.sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return path


# Source certification

def test_manifest_sidecar_mismatch_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{}", encoding="utf-8")
    Path(f"{path}.sha256").write_text(f"{'0' * 64}  {path.name}\n", encoding="utf-8")
    with pytest.raises(SourceCertificationError, match="digest mismatch"):
        verify_manifest_sidecar(path)


def test_manifest_rejects_duplicate_symbol_session(tmp_path: Path) -> None:
    records = [
        {
            "logical_path": "runtime/upstox_candidate_replay/a.parquet",
            "symbol": "NIFTY",
            "session_date": "2024-01-01",
            "actual_sha256": "a" * 64,
            "byte_size": 1,
            "source_record_id": "a",
        },
        {
            "logical_path": "runtime/upstox_candidate_replay/b.parquet",
            "symbol": "NIFTY",
            "session_date": "2024-01-01",
            "actual_sha256": "b" * 64,
            "byte_size": 1,
            "source_record_id": "b",
        },
    ]
    path = _write_manifest(tmp_path, records)
    with pytest.raises(SourceCertificationError, match="duplicate"):
        load_and_verify_manifest(path)


def test_manifest_rejects_path_escape(tmp_path: Path) -> None:
    record = {
        "logical_path": "../outside.parquet",
        "symbol": "NIFTY",
        "session_date": "2024-01-01",
        "actual_sha256": "a" * 64,
        "byte_size": 1,
        "source_record_id": "a",
    }
    path = _write_manifest(tmp_path, [record])
    with pytest.raises(SourceCertificationError, match="unsafe"):
        load_and_verify_manifest(path)


def test_special_session_policy_must_describe_exclusion(tmp_path: Path) -> None:
    record = {
        "logical_path": "runtime/upstox_candidate_replay/a.parquet",
        "symbol": "NIFTY",
        "session_date": "2024-01-01",
        "actual_sha256": "a" * 64,
        "byte_size": 1,
        "source_record_id": "a",
    }
    policy = {
        "policy": "EXCLUDE_SPECIAL_SESSION_WITH_RECORDED_REASON",
        "session_date": "2024-01-02",
        "symbol": "NIFTY",
        "expected_rows": 375,
        "actual_rows": 375,
        "reason": "invalid",
    }
    path = _write_manifest(tmp_path, [record], [policy])
    with pytest.raises(SourceCertificationError, match="complete session"):
        load_and_verify_manifest(path)


def test_development_manifest_excludes_all_later_partitions() -> None:
    payload = {
        "records": [
            {"symbol": "NIFTY", "session_date": "2025-09-05", "logical_path": "a", "actual_sha256": "a"},
            {"symbol": "NIFTY", "session_date": "2025-09-08", "logical_path": "b", "actual_sha256": "b"},
            {"symbol": "NIFTY", "session_date": "2026-07-22", "logical_path": "c", "actual_sha256": "c"},
        ],
        "special_session_policies": [],
    }
    selected = development_manifest_payload(payload, instrument="NIFTY", registry=default_registry())
    assert [record["session_date"] for record in selected["records"]] == ["2025-09-05"]


def test_source_file_hash_and_size_are_reopened(tmp_path: Path) -> None:
    root = tmp_path
    data = root / "runtime" / "upstox_candidate_replay" / "a.bin"
    data.parent.mkdir(parents=True)
    data.write_bytes(b"abc")
    record = {
        "logical_path": "runtime/upstox_candidate_replay/a.bin",
        "actual_sha256": hashlib.sha256(b"abc").hexdigest(),
        "byte_size": 3,
        "source_record_id": "a",
        "session_date": "2024-01-01",
        "symbol": "NIFTY",
    }
    assert verify_record_file(root, record)["byte_size"] == 3
    record["actual_sha256"] = "0" * 64
    with pytest.raises(SourceCertificationError, match="SHA-256 mismatch"):
        verify_record_file(root, record)


def test_source_symlink_is_rejected(tmp_path: Path) -> None:
    root = tmp_path
    authority = root / "runtime" / "upstox_candidate_replay"
    authority.mkdir(parents=True)
    target = root / "target.bin"
    target.write_bytes(b"x")
    link = authority / "link.bin"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(SourceCertificationError, match="symlink"):
        resolve_source_file(root, "runtime/upstox_candidate_replay/link.bin")


# Folds

def test_anchored_folds_are_chronological_and_embargoed() -> None:
    sessions = pd.bdate_range("2024-01-01", periods=30).strftime("%Y-%m-%d")
    folds = generate_anchored_folds(sessions, num_folds=5, embargo_sessions=1)
    assert [fold.fold for fold in folds] == [1, 2, 3, 4, 5]
    for fold in folds:
        assert max(fold.train_sessions) < min(fold.validation_sessions)
        assert not set(fold.train_sessions) & set(fold.validation_sessions)
        ordered = sorted(set(sessions))
        expected_previous = ordered[ordered.index(fold.validation_start) - 1]
        assert fold.embargo_sessions == (expected_previous,)


def test_fold_generation_is_deterministic() -> None:
    sessions = list(reversed(pd.bdate_range("2024-01-01", periods=30).strftime("%Y-%m-%d")))
    first = [fold.to_dict() for fold in generate_anchored_folds(sessions, num_folds=4)]
    second = [fold.to_dict() for fold in generate_anchored_folds(sessions, num_folds=4)]
    assert first == second
    assert fold_manifest_hash(first) == fold_manifest_hash(second)


def test_nested_folds_never_use_outer_validation_in_inner_training() -> None:
    frame = pd.DataFrame({"session_date": pd.bdate_range("2024-01-01", periods=72).strftime("%Y-%m-%d")})
    nested = generate_nested_folds(frame, outer_folds=5, inner_folds=4)
    for item in nested:
        outer_validation = set(item["outer"]["validation_sessions"])
        for inner in item["inner"]:
            assert not outer_validation & set(inner["train_sessions"])
            assert not outer_validation & set(inner["validation_sessions"])


def test_too_many_folds_fail_closed() -> None:
    with pytest.raises(ValueError, match="too few sessions"):
        generate_anchored_folds(["2024-01-01", "2024-01-02"], num_folds=3)


