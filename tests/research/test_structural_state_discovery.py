from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_structural_state_discovery import (
    DEFAULT_KITE_ARCHIVE,
    DiscoveryError,
    build_features,
    load_kite,
    run,
    split_sessions,
)


def test_fake_kite_archive_fails_closed(tmp_path: Path) -> None:
    fake = tmp_path / "kite.zip"
    fake.write_bytes(b"bad")
    with pytest.raises(DiscoveryError, match="hash mismatch"):
        load_kite(fake)


def test_split_freezes_latest_100_sessions() -> None:
    sessions = [{"session": f"2025-01-{i:02d}"} for i in range(1, 121)]
    split = split_sessions(sessions)
    assert len(split["holdout"]) == 100
    assert split["holdout_opened"] is False
    assert set(split["development"]).isdisjoint(split["holdout"])
    assert set(split["validation"]).isdisjoint(split["holdout"])


def test_real_kite_feature_matrix_has_predeclared_decision_times() -> None:
    if not DEFAULT_KITE_ARCHIVE.is_file():
        pytest.fail("authoritative Kite archive missing")
    bars, _, sessions = load_kite(DEFAULT_KITE_ARCHIVE)
    features = build_features(bars, sessions[:8])
    assert not features.empty
    assert set(features["decision_time"]).issubset({"09:45", "10:30", "11:30", "13:00", "14:00"})
    assert (features["execution_eligibility"] == False).all()  # noqa: E712
    assert (features["research_only"] == True).all()  # noqa: E712


def test_campaign_writes_required_artifacts(tmp_path: Path) -> None:
    if not DEFAULT_KITE_ARCHIVE.is_file():
        pytest.fail("authoritative Kite archive missing")
    result = run(tmp_path / "evidence", DEFAULT_KITE_ARCHIVE)
    assert result["final_verdict"] in {"NO_STABLE_STATE_EDGE_FOUND", "DISCOVERY_ONLY_NOT_VALIDATED"}
    required = [
        "source/source_authority.json",
        "source/split_freeze.json",
        "contracts/feature_contract.json",
        "features/feature_matrix.parquet",
        "discovery/complete_hypothesis_ledger.parquet",
        "discovery/quantile_scan.json",
        "candidates/frozen_candidate_rules.json",
        "evaluation/development_results.json",
        "audit/final_verdict.json",
        "report/FINAL_REPORT.md",
    ]
    for rel in required:
        assert (tmp_path / "evidence" / rel).is_file()
        assert (tmp_path / "evidence" / f"{rel}.sha256").is_file()
