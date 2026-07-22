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
    StabilityConfig,
    canonical_hash,
    is_forbidden_feature,
    require_causal_features,
)
from research.ml_strategy_discovery_v2.data import (
    ConfirmationAuthorizationError,
    DatasetRegistryViolation,
    TokenReplayViolation,
    consume_confirmation_authorization,
    default_registry,
    issue_confirmation_authorization,
    load_development_for_selection,
    load_registry,
    locked_confirmation_metadata,
    select_development_bars,
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


# Contracts and configuration

def test_canonical_hash_is_order_independent() -> None:
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})


def test_forbidden_features_cover_labels_timestamps_and_source_ids() -> None:
    assert is_forbidden_feature("label_return_r")
    assert is_forbidden_feature("decision_timestamp")
    assert is_forbidden_feature("source_manifest_record_id")
    assert not is_forbidden_feature("distance_from_vwap_atr")


def test_require_causal_features_rejects_duplicates_and_leakage() -> None:
    with pytest.raises(ValueError, match="unique"):
        require_causal_features(["f1", "f1"])
    with pytest.raises(ValueError, match="forbidden"):
        require_causal_features(["f1", "future_return"])


def test_stability_config_rejects_invalid_iterations() -> None:
    with pytest.raises(ValueError, match="at least 100"):
        StabilityConfig(bootstrap_iterations=99)


# Dataset registry and confirmation lock

def test_default_registry_classifies_all_frozen_boundaries() -> None:
    registry = default_registry()
    assert registry.classify("2025-09-05") == DEVELOPMENT
    assert registry.classify("2025-09-08") == VALIDATION_CONSUMED
    assert registry.classify("2026-02-06") == HOLDOUT_LOCKED
    assert registry.classify("2026-07-21") == FRESH_CONSUMED
    assert registry.classify("2026-07-22") == FRESH_LOCKED


def test_load_registry_accepts_exact_contract(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(_registry_payload()), encoding="utf-8")
    registry = load_registry(path)
    assert registry.classify("2024-01-01") == DEVELOPMENT
    assert registry.source_hash == hashlib.sha256(path.read_bytes()).hexdigest()


def test_load_registry_rejects_boundary_mutation(tmp_path: Path) -> None:
    payload = _registry_payload()
    payload["ranges"][0]["end"] = "2025-09-06"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DatasetRegistryViolation, match="boundaries"):
        load_registry(path)


def test_development_loader_rejects_consumed_and_locked_rows() -> None:
    frame = pd.DataFrame(
        {"session_date": ["2024-01-01", "2025-09-08", "2026-02-06", "2026-07-22"]}
    )
    with pytest.raises(DatasetRegistryViolation, match="forbidden partitions"):
        load_development_for_selection(frame)


def test_development_loader_accepts_only_development() -> None:
    frame = pd.DataFrame({"session_date": ["2024-01-01", "2025-09-05"], "x": [1, 2]})
    selected = load_development_for_selection(frame)
    assert selected["v2_dataset"].eq(DEVELOPMENT).all()


def test_raw_bar_selection_happens_before_labels() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2025-09-05 09:15"), pd.Timestamp("2025-09-08 09:15")],
            "open": [1.0, 2.0],
        }
    )
    selected = select_development_bars(frame, registry=default_registry())
    assert selected["session_date"].tolist() == ["2025-09-05"]


def test_locked_confirmation_metadata_strips_outcomes() -> None:
    frame = pd.DataFrame(
        {
            "session_date": ["2026-07-21", "2026-07-22"],
            "instrument": ["NIFTY", "NIFTY"],
            "label_return_r": [1.0, -1.0],
            "expectancy": [1.0, -1.0],
            "source_sha256": ["a", "b"],
        }
    )
    metadata = locked_confirmation_metadata(frame)
    assert set(metadata["v2_dataset"]) == {FRESH_CONSUMED, FRESH_LOCKED}
    assert "label_return_r" not in metadata
    assert "expectancy" not in metadata


def test_confirmation_authorization_is_bound_and_one_time(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    token = issue_confirmation_authorization(
        candidate_bundle_hash="a" * 64,
        fresh_manifest_hash="b" * 64,
        code_sha="c" * 40,
        side="LONG",
        evaluation_id="eval-1",
        state_path=state,
    )
    consume_confirmation_authorization(
        token=token,
        candidate_bundle_hash="a" * 64,
        fresh_manifest_hash="b" * 64,
        code_sha="c" * 40,
        side="LONG",
        evaluation_id="eval-1",
        state_path=state,
    )
    with pytest.raises(TokenReplayViolation):
        consume_confirmation_authorization(
            token=token,
            candidate_bundle_hash="a" * 64,
            fresh_manifest_hash="b" * 64,
            code_sha="c" * 40,
            side="LONG",
            evaluation_id="eval-1",
            state_path=state,
        )


def test_confirmation_authorization_rejects_wrong_binding(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    token = issue_confirmation_authorization(
        candidate_bundle_hash="a" * 64,
        fresh_manifest_hash="b" * 64,
        code_sha="c" * 40,
        side="SHORT",
        evaluation_id="eval-1",
        state_path=state,
    )
    with pytest.raises(ConfirmationAuthorizationError, match="binding mismatch"):
        consume_confirmation_authorization(
            token=token,
            candidate_bundle_hash="d" * 64,
            fresh_manifest_hash="b" * 64,
            code_sha="c" * 40,
            side="SHORT",
            evaluation_id="eval-1",
            state_path=state,
        )


