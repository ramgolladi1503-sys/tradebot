from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.ml_strategy_discovery_v2 import artifacts, pipeline
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
from research.ml_strategy_discovery_v2.controls import run_negative_controls
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
from research.ml_strategy_discovery_v2.folds import (
    fold_manifest_hash,
    generate_anchored_folds,
    generate_nested_folds,
)
from research.ml_strategy_discovery_v2.freeze import (
    candidate_bundle,
    write_frozen_registry,
)
from research.ml_strategy_discovery_v2.gates import (
    base_rate_gate,
    bootstrap_gate,
    concentration_gate,
    concentration_metrics,
    fold_gate,
    imputation_dependence,
    performance_metrics,
    session_bootstrap_expectancy,
    support_gate,
)
from research.ml_strategy_discovery_v2.model import (
    RuleReproductionError,
    fit_imputer,
    generate_candidates,
    rule_mask,
    semantic_frame_hash,
)
from research.ml_strategy_discovery_v2.source import (
    SourceCertificationError,
    development_manifest_payload,
    load_and_verify_manifest,
    resolve_source_file,
    verify_manifest_sidecar,
    verify_record_file,
)
from research.ml_strategy_discovery_v2.stability import (
    benjamini_hochberg,
    jaccard_selected_rows,
    max_statistic_test,
    permuted_labels_by_session,
    recurrence_summary,
    rule_similarity,
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


# Pipeline, artifacts, and freeze

def test_pipeline_no_edge_returns_no_candidate() -> None:
    sessions = pd.bdate_range("2024-01-01", periods=72).strftime("%Y-%m-%d")
    frame = pd.DataFrame(
        {
            "session_date": np.repeat(sessions, 3),
            "decision_timestamp": pd.date_range("2024-01-01", periods=len(sessions) * 3, freq="min"),
            "f1": np.linspace(-1, 1, len(sessions) * 3),
            "label_return_r": np.zeros(len(sessions) * 3),
            "trend_regime": 0.0,
            "volatility_regime": 0.0,
            "gap_regime": 0.0,
            "time_regime": 0.0,
        }
    )
    config = StabilityConfig(
        min_rows=5,
        min_sessions=3,
        bootstrap_iterations=100,
        permutation_iterations=100,
    )
    result = pipeline.run_stability_first_discovery(frame, side="LONG", features=["f1"], config=config)
    assert result["verdict"] == "NO_STABLE_CANDIDATE"
    assert result["candidate"] is None
    assert "NO_OUTER_CONSENSUS_CANDIDATE" in result["rejection_reasons"]


def test_pipeline_verdict_is_gate_driven(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = _frame(sessions=72, rows_per_session=5)
    candidate = _candidate(0.5)
    candidate.update({"feature_names": ["f1"], "source_dataset_hash": "a" * 64})
    monkeypatch.setattr(pipeline, "_select_candidate_on_inner_folds", lambda *a, **k: (candidate, [candidate], 1))
    monkeypatch.setattr(pipeline, "max_statistic_test", lambda *a, **k: {"candidates": [{"rule_hash": candidate["rule_hash"], "passes_adjusted_significance": True}], "hypothesis_count": 1})
    monkeypatch.setattr(pipeline, "recurrence_summary", lambda *a, **k: {"passes_recurrence": True})
    monkeypatch.setattr(pipeline, "run_negative_controls", lambda *a, **k: {"passes": True, "rejection_reasons": []})
    monkeypatch.setattr(pipeline, "support_gate", lambda *a, **k: (True, []))
    monkeypatch.setattr(pipeline, "base_rate_gate", lambda *a, **k: (True, []))
    monkeypatch.setattr(pipeline, "fold_gate", lambda *a, **k: (True, [], {"ok": True}))
    monkeypatch.setattr(pipeline, "concentration_gate", lambda *a, **k: (True, []))
    monkeypatch.setattr(pipeline, "imputation_gate", lambda *a, **k: (True, []))
    monkeypatch.setattr(pipeline, "bootstrap_gate", lambda *a, **k: (False, ["BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE"]))
    config = StabilityConfig(min_rows=5, min_sessions=3, bootstrap_iterations=100, permutation_iterations=100)
    failed = pipeline.run_stability_first_discovery(frame, side="LONG", features=["f1"], config=config)
    assert failed["candidate"] is None
    assert "BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE" in failed["rejection_reasons"]
    monkeypatch.setattr(pipeline, "bootstrap_gate", lambda *a, **k: (True, []))
    passed = pipeline.run_stability_first_discovery(frame, side="LONG", features=["f1"], config=config)
    assert passed["candidate"] is not None
    assert passed["verdict"] == "ONE_LONG_V2_CANDIDATE_FROZEN"


def test_semantic_hash_ignores_generated_at() -> None:
    left = {"generated_at": "a", "value": 1}
    right = {"generated_at": "b", "value": 1}
    assert artifacts.semantic_hash(left) == artifacts.semantic_hash(right)


def test_semantic_manifest_identity_ignores_raw_timestamp_hashes(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    artifacts.write_json(first / "a.json", {"generated_at": "a", "value": 1})
    artifacts.write_json(second / "a.json", {"generated_at": "b", "value": 1})
    one = artifacts.build_semantic_hash_manifest(first)
    two = artifacts.build_semantic_hash_manifest(second)
    assert one["manifest_semantic_sha256"] == two["manifest_semantic_sha256"]


def test_candidate_bundle_identity_is_deterministic() -> None:
    kwargs = dict(
        candidate=_candidate(),
        side="LONG",
        source_manifest_hash="a" * 64,
        development_dataset_hash="b" * 64,
        feature_schema_hash="c" * 64,
        fold_manifest_hash="d" * 64,
        search_space_hash="e" * 64,
        multiple_testing={"p": 0.01},
        recurrence={"passes": True},
        concentration={"ok": True},
        bootstrap={"lower_95": 0.1},
        imputation_dependence={"fraction": 0.0},
        controls={"passes": True},
        code_sha="f" * 40,
    )
    assert candidate_bundle(**kwargs) == candidate_bundle(**kwargs)


def test_frozen_registry_rejects_duplicate_side(tmp_path: Path) -> None:
    bundle = {"side": "LONG"}
    with pytest.raises(ValueError, match="at most one"):
        write_frozen_registry(
            tmp_path / "frozen.json",
            bundles=[bundle, bundle],
            code_sha="a" * 40,
            input_hashes={"x": "b" * 64},
            seeds=[42],
        )


def test_frozen_registry_never_issues_confirmation_token(tmp_path: Path) -> None:
    payload = write_frozen_registry(
        tmp_path / "frozen.json",
        bundles=[],
        code_sha="a" * 40,
        input_hashes={"x": "b" * 64},
        seeds=[42],
    )
    assert payload["verdict"] == "NO_STABLE_CANDIDATE"
    assert payload["confirmation_token_issued"] is False


def test_v2_source_contains_no_placeholder_or_pass_only_markers() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = list((root / "research" / "ml_strategy_discovery_v2").glob("*.py"))
    paths += [root / "scripts" / "run_ml_strategy_discovery_v2.py"]
    forbidden = [
        "assert" + " True",
        "Simulated",
        "simulated",
        "ss_hash",
        "f_hash",
        "generic_token",
    ]
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, f"placeholder marker {marker!r} in {path}"


def test_runner_uses_declared_permutation_argument() -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_ml_strategy_discovery_v2.py"
    if not script.exists():
        pytest.skip("runner not present in isolated unit fixture")
    text = script.read_text(encoding="utf-8")
    assert "args.permutation_iterations" in text
    assert "args.permutations" not in text
