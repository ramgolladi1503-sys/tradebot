from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from scripts.run_structural_state_discovery import (
    DEFAULT_KITE_ARCHIVE,
    DiscoveryError,
    apply_rule,
    build_matrices,
    load_kite,
    outer_folds,
    quantile_rules,
    run,
    sparse_results,
    split_sessions,
    target_stop_label,
    tree_rules,
    cluster_states,
    TARGET_FAMILIES,
)


def test_fake_archive_hash_rejected(tmp_path: Path) -> None:
    fake = tmp_path / "kite.zip"
    fake.write_bytes(b"bad")
    with pytest.raises(DiscoveryError, match="hash mismatch"):
        load_kite(fake)


def _tiny_parquet(session: str, symbol: str, duplicate_conflict: bool = False) -> bytes:
    rows = []
    start = pd.Timestamp(f"{session} 09:15", tz="Asia/Kolkata").tz_convert("UTC")
    for i in range(70):
        ts = start + pd.Timedelta(minutes=5 * i)
        rows.append({"date": ts, "fetch_date": session, "open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i})
    rows.append(rows[-1].copy())
    if duplicate_conflict:
        rows[-1]["high"] += 10
        rows[-1]["close"] += 5
    df = pd.DataFrame(rows)
    bio = io.BytesIO()
    df.to_parquet(bio, index=False)
    return bio.getvalue()


def test_duplicate_reconciliation_rejects_conflicting_ohlc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = tmp_path / "kite.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for sym in ("NIFTY", "BANKNIFTY", "SENSEX"):
            zf.writestr(f"x/underlying/{sym}_2026.parquet", _tiny_parquet("2026-01-01", sym, duplicate_conflict=(sym == "NIFTY")))
    import scripts.run_structural_state_discovery as mod
    monkeypatch.setattr(mod, "EXPECTED_KITE_HASH", mod.file_sha256(archive))
    bars, accepted, sessions, rejected, dupes = load_kite(archive)
    assert any(r["reason"] == "conflicting_duplicate_ohlc" for r in rejected)
    assert dupes["duplicate_key_count"] >= 1
    assert all(a["symbol"] != "NIFTY" for a in accepted)


def test_real_kite_features_repair_leakage_and_outcomes() -> None:
    if not DEFAULT_KITE_ARCHIVE.is_file():
        pytest.fail("authoritative Kite archive missing")
    bars, _, sessions, _, _ = load_kite(DEFAULT_KITE_ARCHIVE)
    features, outcomes = build_matrices(bars, sessions[:14])
    assert not features.empty
    assert len(features) == len(outcomes)
    assert set(features["previous_inside_outside_state"]).issubset({"INSIDE", "OUTSIDE", "HIGHER_HIGH_ONLY", "LOWER_LOW_ONLY", "NEITHER"})
    assert (features["previous_true_range_bps"] >= 0).all()
    assert (features["relative_acceleration"].abs() < 1000).all()
    assert "30m_target_10_stop_10_label" in outcomes.columns
    assert "60m_target_20_stop_20_label" in outcomes.columns
    assert set(outcomes["30m_target_10_stop_10_label"].unique()).issubset({"TARGET_BEFORE_STOP", "STOP_BEFORE_TARGET", "AMBIGUOUS_SAME_BAR", "NEITHER"})
    assert (pd.to_datetime(features["entry_timestamp"]) >= pd.to_datetime(features["decision_timestamp"])).all()
    assert set(TARGET_FAMILIES) == {"CONTINUATION", "REVERSAL", "ABSOLUTE_EXPANSION", "RAW_LONG", "RAW_SHORT"}
    assert TARGET_FAMILIES["ABSOLUTE_EXPANSION"]["hurdle_bps"] == 20.0


def test_target_stop_same_bar_ambiguity_not_optimistic() -> None:
    day = pd.DataFrame([
        {"interval_start": pd.Timestamp("2026-01-01 09:45", tz="Asia/Kolkata"), "high": 101.0, "low": 99.0},
    ])
    assert target_stop_label(day, day.iloc[0].interval_start, 100.0, 1, 50, 50, 30) == "AMBIGUOUS_SAME_BAR"


def test_folds_exclude_validation_and_are_expanding() -> None:
    sessions = [f"2026-01-{i:02d}" for i in range(1, 61)]
    split = split_sessions(sessions)
    folds = outer_folds(split["discovery_sessions"])
    validation = set(split["final_retrospective_validation_block"])
    previous = 0
    for fold in folds:
        assert fold["train_end"] < fold["test_start"]
        assert set(fold["train_sessions"]).isdisjoint(fold["test_sessions"])
        assert validation.isdisjoint(fold["train_sessions"])
        assert validation.isdisjoint(fold["test_sessions"])
        assert len(fold["train_sessions"]) > previous
        previous = len(fold["train_sessions"])


def test_real_lanes_fit_models_without_contradictory_rules() -> None:
    if not DEFAULT_KITE_ARCHIVE.is_file():
        pytest.fail("authoritative Kite archive missing")
    bars, _, sessions, _, _ = load_kite(DEFAULT_KITE_ARCHIVE)
    features, outcomes = build_matrices(bars, sessions[:45])
    joined = features.merge(outcomes, on=["row_id", "source_id", "session", "symbol", "decision_time", "entry_timestamp"])
    train = joined[joined["session"].isin(sorted(joined.session.unique())[:30])]
    test = joined[joined["session"].isin(sorted(joined.session.unique())[30:40])]
    qrules = quantile_rules(train, cap=20)
    assert qrules
    for rule in qrules:
        assert apply_rule(test, rule["predicates"]).dtype == bool
        assert len({(p["feature"], p["op"], str(p["value"])) for p in rule["predicates"]}) == len(rule["predicates"])
    assert tree_rules(train, "CONTINUATION")
    selected, sparse, sparse_rules = sparse_results(train, test, "RAW_SHORT")
    assert isinstance(selected, list)
    assert "sparse_prediction" in sparse.columns
    assert {r["lane"] for r in sparse_rules} == {"sparse"}
    states, clusters = cluster_states(train, test, "ABSOLUTE_EXPANSION")
    assert states
    assert "cluster" in clusters.columns


def test_campaign_artifacts_truthful_verdict(tmp_path: Path) -> None:
    if not DEFAULT_KITE_ARCHIVE.is_file():
        pytest.fail("authoritative Kite archive missing")
    out = tmp_path / "evidence"
    result = run(out, DEFAULT_KITE_ARCHIVE, max_sessions=45, permutations=10)
    assert result["final_verdict"] in {"NO_STABLE_STATE_EDGE_FOUND_IN_PREDECLARED_SEARCH", "DISCOVERY_ONLY_NOT_VALIDATED", "RETROSPECTIVE_VALIDATED_STATE_CANDIDATE", "READY_FOR_PROSPECTIVE_SHADOW"}
    assert result["oracle"] == "PASS"
    assert result["mutations"] is True
    required = [
        "source/source_authority.json",
        "source/rejected_file_manifest.json",
        "source/duplicate_reconciliation.json",
        "contracts/statistics_contract.json",
        "features/feature_matrix.parquet",
        "folds/discovery_validation_split.json",
        "folds/inner_selection_decisions.json",
        "discovery/complete_hypothesis_ledger.parquet",
        "discovery/stable_rule_templates.parquet",
        "discovery/aggregated_template_metrics.parquet",
        "discovery/tree_rules.parquet",
        "discovery/sparse_model_results.parquet",
        "discovery/cluster_states.parquet",
        "discovery/outer_test_memberships.parquet",
        "evaluation/matched_controls.parquet",
        "evaluation/negative_controls.json",
        "freeze/pre_validation_candidate_bundle.json",
        "validation/final_retrospective_validation.json",
        "audit/independent_oracle.json",
        "audit/mutation_tests.json",
        "audit/determinism.json",
        "audit/final_verdict.json",
        "run-a/features/feature_matrix.parquet",
        "run-b/features/feature_matrix.parquet",
    ]
    for rel in required:
        assert (out / rel).is_file(), rel
        assert (out / f"{rel}.sha256").is_file(), rel
    verdict = json.loads((out / "audit/final_verdict.json").read_text())
    assert verdict["v3_broad_no_edge_invalidated"] is True
    ledger = pd.read_parquet(out / "discovery/complete_hypothesis_ledger.parquet")
    assert set(ledger["target_family"]) == set(TARGET_FAMILIES)
    assert {"quantile", "tree", "sparse", "cluster"}.issubset(set(ledger["lane"]))
    aggregated = pd.read_parquet(out / "discovery/aggregated_template_metrics.parquet")
    assert "rule_template_id" in aggregated.columns
