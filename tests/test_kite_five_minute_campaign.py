from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from research.kite_five_minute_campaign import (
    ProspectiveAccessError,
    ProspectiveDataGovernance,
    audit_campaign,
    build_exposure_ledger,
    certify_archive,
    run_campaign,
)
from research.kite_five_minute_campaign.common import file_sha256
from research.kite_five_minute_campaign.engine import build_five_minute_features, truncation_oracle


def _bars(date: str, instrument: str, *, rows: int = 76) -> pd.DataFrame:
    ts = pd.date_range(f"{date} 09:15", periods=rows, freq="5min", tz="Asia/Kolkata")
    base = {"NIFTY": 22000, "BANKNIFTY": 48000, "SENSEX": 73000}[instrument]
    return pd.DataFrame({
        "timestamp": ts,
        "open": [base + i for i in range(rows)],
        "high": [base + i + 2 for i in range(rows)],
        "low": [base + i - 2 for i in range(rows)],
        "close": [base + i + 1 for i in range(rows)],
    })


def _archive(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    for inst in ("NIFTY", "BANKNIFTY", "SENSEX"):
        day = source / "kite_candidate_replay" / "2026-07-01"
        day.mkdir(parents=True, exist_ok=True)
        _bars("2026-07-01", inst).to_parquet(day / f"{inst}_kite_5m_20260701.parquet")
    _bars("2026-07-01", "NIFTY").assign(mock=True).to_parquet(
        source / "kite_candidate_replay" / "2026-07-01" / "NIFTY_OPT_MOCK_20260701.parquet"
    )
    (source / "__MACOSX").mkdir()
    (source / "__MACOSX" / "._junk").write_text("metadata", encoding="utf-8")
    archive = tmp_path / "kite_candidate_replay.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in source.rglob("*"):
            zf.write(path, path.relative_to(source))
    return archive


def test_archive_classification_manifest_hashing_and_mock_exclusion(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    summary = certify_archive(archive, tmp_path / "out", commit="abc123")
    assert summary["accepted_files"] == 3
    assert summary["rejected_counts_by_reason"]["MOCK_DATA"] == 1
    assert summary["rejected_counts_by_reason"]["APPLE_METADATA"] == 1
    manifest_path = tmp_path / "out/research/kite_five_minute_campaign/input/accepted_underlying_manifest.json"
    assert manifest_path.with_name(manifest_path.name + ".sha256").is_file()


def test_five_minute_alignment_missing_rejection_and_truncation(tmp_path: Path) -> None:
    manifest = []
    for inst in ("NIFTY", "BANKNIFTY", "SENSEX"):
        path = tmp_path / f"{inst}.parquet"
        _bars("2026-07-01", inst).to_parquet(path)
        manifest.append({"absolute_path": str(path), "instrument": inst, "trading_date": "2026-07-01", "relative_path": path.name})
    result = build_five_minute_features(manifest)
    assert len(result.rows) == 1
    assert result.rows.iloc[0]["lineage"]["NIFTY"]["timestamp"].endswith("+05:30")
    assert truncation_oracle(manifest, result.rows.iloc[0]["decision_timestamp"])
    missing = build_five_minute_features(manifest[:2])
    assert missing.rows.empty
    assert "missing index components" in missing.rejected[0]["reason"]


def test_sealed_data_denial_release_binding_and_consumed_guard(tmp_path: Path) -> None:
    gov = ProspectiveDataGovernance(tmp_path / "prospective")
    sealed = gov.sealed / "2026-08-01.parquet"
    sealed.write_bytes(b"sealed")
    assert gov.enumerate_development_dates() == []
    with pytest.raises(ProspectiveAccessError):
        gov.read_development_file(sealed)
    with pytest.raises(ProspectiveAccessError):
        gov.aggregate_strategy_dependent_stats()
    assert gov.schema_health()["sealed_file_count"] == 1
    release = gov.create_release(
        release_id="r1",
        candidate_bundle_hash="a" * 64,
        strategy_code_commit="abc123",
        configuration_hash="b" * 64,
        date_range=["2026-08-01", "2026-08-01"],
        purpose="confirmation",
        authority="human",
    )
    with pytest.raises(ProspectiveAccessError):
        gov.consume_release(release, candidate_bundle_hash="c" * 64)
    gov.consume_release(release, candidate_bundle_hash="a" * 64)
    with pytest.raises(ProspectiveAccessError):
        gov.consume_release(release, candidate_bundle_hash="a" * 64)


def test_exposure_ledger_and_campaign_determinism_and_audit(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    certify_archive(archive, tmp_path, commit="abc123")
    input_dir = tmp_path / "research/kite_five_minute_campaign/input"
    manifest = json.loads((input_dir / "accepted_underlying_manifest.json").read_text())
    extract_root = input_dir / "extracted"
    for row in manifest:
        row["absolute_path"] = str(extract_root / row["relative_path"])
    ledger = build_exposure_ledger(tmp_path, manifest, tmp_path / "research/data_governance", commit="abc123")
    assert ledger["entry_count"] == 3
    source_hash = file_sha256(input_dir / "accepted_underlying_manifest.json")
    first = run_campaign(manifest, tmp_path / "run_a", source_manifest_hash=source_hash, code_commit="abc123")
    second = run_campaign(manifest, tmp_path / "run_b", source_manifest_hash=source_hash, code_commit="abc123")
    assert first == second
    assert first["total_variants"] == 24
    assert first["verdict"] == "NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET"
    audit = audit_campaign(input_dir, tmp_path / "run_a", tmp_path / "audit.json")
    assert audit["matches_primary_verdict"] is True
    assert audit["candidate_count"] == 0
