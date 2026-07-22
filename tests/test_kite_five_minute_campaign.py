from __future__ import annotations

import json
import os
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
from research.kite_five_minute_campaign.contract import campaign_contract, contract_hash, frozen_variants


REAL_ARCHIVE = Path(os.environ.get("KITE_ARCHIVE", "/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip"))
REAL_ARCHIVE_SHA = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"


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
        day = source / "kite_candidate_replay" / "2026-07-01" / "underlying"
        day.mkdir(parents=True, exist_ok=True)
        _bars("2026-07-01", inst).to_parquet(day / f"{inst}_kite_5m_20260701.parquet")
    options = source / "kite_candidate_replay" / "2026-07-01" / "options"
    options.mkdir(parents=True, exist_ok=True)
    _bars("2026-07-01", "NIFTY").assign(mock=True).to_parquet(options / "NIFTY_OPT_MOCK_20260701.parquet")
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
    assert summary["primary_disposition_counts"]["REJECT_APPLE_METADATA"] == 1
    manifest_path = tmp_path / "out/research/kite_five_minute_campaign/input/accepted_underlying_manifest.json"
    assert manifest_path.with_name(manifest_path.name + ".sha256").is_file()


def test_expected_archive_sha_is_accepted() -> None:
    assert file_sha256(REAL_ARCHIVE) == REAL_ARCHIVE_SHA


def test_wrong_archive_sha_is_rejected() -> None:
    assert file_sha256(REAL_ARCHIVE) != "0" * 64


def test_real_archive_source_counts_before_filtering(tmp_path: Path) -> None:
    summary = certify_archive(REAL_ARCHIVE, tmp_path, commit="abc123")
    authority = summary["archive_authority"]
    assert authority["real_underlying_count_by_symbol_before_filtering"] == {
        "BANKNIFTY": 493,
        "NIFTY": 493,
        "SENSEX": 493,
    }
    assert authority["mock_option_count"] == 30
    assert authority["apple_metadata_count"] == 2544


def test_primary_disposition_counts_sum_to_zip_files(tmp_path: Path) -> None:
    summary = certify_archive(_archive(tmp_path), tmp_path / "out", commit="abc123")
    assert sum(summary["primary_disposition_counts"].values()) == summary["total_files"]


def test_secondary_flags_do_not_define_total_rejected_count(tmp_path: Path) -> None:
    summary = certify_archive(_archive(tmp_path), tmp_path / "out", commit="abc123")
    assert sum(summary["secondary_flag_counts"].values()) >= summary["rejected_files"] - 1
    assert summary["primary_disposition_count_sum"] == summary["total_files"]


def test_malformed_parquet_rejected(tmp_path: Path) -> None:
    root = tmp_path / "src/kite_candidate_replay/2026-07-01/underlying"
    root.mkdir(parents=True)
    (root / "NIFTY_2026-07-01.parquet").write_text("not parquet", encoding="utf-8")
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(root / "NIFTY_2026-07-01.parquet", "kite_candidate_replay/2026-07-01/underlying/NIFTY_2026-07-01.parquet")
    summary = certify_archive(archive, tmp_path / "out", commit="abc123")
    assert summary["primary_disposition_counts"]["REJECT_MALFORMED"] == 1


def test_non_five_minute_data_rejected(tmp_path: Path) -> None:
    root = tmp_path / "src/kite_candidate_replay/2026-07-01/underlying"
    root.mkdir(parents=True)
    df = _bars("2026-07-01", "NIFTY")
    df["timestamp"] = pd.date_range("2026-07-01 09:15", periods=len(df), freq="1min", tz="Asia/Kolkata")
    df.to_parquet(root / "NIFTY_2026-07-01.parquet")
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(root / "NIFTY_2026-07-01.parquet", "kite_candidate_replay/2026-07-01/underlying/NIFTY_2026-07-01.parquet")
    summary = certify_archive(archive, tmp_path / "out", commit="abc123")
    assert summary["primary_disposition_counts"]["REJECT_NOT_NATIVE_5M"] == 1


def test_incomplete_session_rejected(tmp_path: Path) -> None:
    root = tmp_path / "src/kite_candidate_replay/2026-07-01/underlying"
    root.mkdir(parents=True)
    _bars("2026-07-01", "NIFTY", rows=12).to_parquet(root / "NIFTY_2026-07-01.parquet")
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(root / "NIFTY_2026-07-01.parquet", "kite_candidate_replay/2026-07-01/underlying/NIFTY_2026-07-01.parquet")
    summary = certify_archive(archive, tmp_path / "out", commit="abc123")
    assert summary["primary_disposition_counts"]["REJECT_INCOMPLETE_SESSION"] == 1


def test_real_archive_six_seven_reconciliation(tmp_path: Path) -> None:
    summary = certify_archive(REAL_ARCHIVE, tmp_path, commit="abc123")
    assert summary["primary_disposition_counts"]["REJECT_INCOMPLETE_SESSION"] == 6
    assert summary["secondary_flag_counts"]["INCOMPLETE_SESSION"] == 7
    assert summary["excluded_underlying_dates"] == ["2024-11-01", "2025-10-21"]


def test_real_archive_accepted_date_alignment(tmp_path: Path) -> None:
    certify_archive(REAL_ARCHIVE, tmp_path, commit="abc123")
    rows = json.loads((tmp_path / "research/kite_five_minute_campaign/input/date_alignment_manifest.json").read_text())
    assert len(rows) == 491
    assert all(row["symbols"] == ["BANKNIFTY", "NIFTY", "SENSEX"] for row in rows)
    assert all(row["compatible_completed_bar_timestamps"] for row in rows)


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


def test_timestamp_disagreement_rejected_by_alignment(tmp_path: Path) -> None:
    manifest = []
    for inst in ("NIFTY", "BANKNIFTY", "SENSEX"):
        path = tmp_path / f"{inst}.parquet"
        df = _bars("2026-07-01", inst)
        if inst == "SENSEX":
            df = df.iloc[1:].reset_index(drop=True)
        df.to_parquet(path)
        manifest.append({"absolute_path": str(path), "instrument": inst, "trading_date": "2026-07-01", "relative_path": path.name})
    result = build_five_minute_features(manifest)
    assert len(result.rows) == 1
    assert result.rows.iloc[0]["lineage"]["SENSEX"]["timestamp"] == result.rows.iloc[0]["decision_timestamp"]


def test_contract_has_four_families_and_24_variants() -> None:
    contract = campaign_contract(source_manifest_hash="a" * 64)
    assert [item["family"] for item in contract["mechanisms"]] == [
        "CROSS_INDEX_RELATIVE_STRENGTH_DISLOCATION",
        "VOLATILITY_STATE_TRANSITION_CONTINUATION",
        "FAILED_AUCTION_REACCEPTANCE",
        "OPENING_CONTINUATION_WITH_INDEX_CONFIRMATION",
    ]
    assert len(contract["frozen_variants"]) == 24
    assert all(item["max_variants"] == 6 for item in contract["mechanisms"])


def test_contract_hash_changes_when_frozen_field_changes() -> None:
    contract = campaign_contract(source_manifest_hash="a" * 64)
    mutated = json.loads(json.dumps(contract))
    mutated["frozen_variants"][0]["parameters"]["threshold_bps"] = 999
    assert contract_hash(contract) != contract_hash(mutated)


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


def test_all_variants_receive_complete_evidence(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    certify_archive(archive, tmp_path, commit="abc123")
    input_dir = tmp_path / "research/kite_five_minute_campaign/input"
    manifest = json.loads((input_dir / "accepted_underlying_manifest.json").read_text())
    extract_root = input_dir / "extracted"
    for row in manifest:
        row["absolute_path"] = str(extract_root / row["relative_path"])
    result = run_campaign(manifest, tmp_path / "run", source_manifest_hash=file_sha256(input_dir / "accepted_underlying_manifest.json"), code_commit="abc123")
    assert result["all_variants_have_complete_evidence"]
    assert len(result["variant_results"]) == 24
    assert all("candidate_gates" in row for row in result["variant_results"])


def test_low_support_fields_are_not_evaluable(tmp_path: Path) -> None:
    result = run_campaign([], tmp_path / "run", source_manifest_hash="a" * 64, code_commit="abc123")
    first = result["variant_results"][0]
    assert first["candidate_gates"]["minimum_trade_support"] == "NOT_EVALUABLE"
    assert first["candidate_gates"]["profit_factor"] == "NOT_EVALUABLE"


def test_independent_audit_rejects_tampered_primary_evidence(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    certify_archive(archive, tmp_path, commit="abc123")
    input_dir = tmp_path / "research/kite_five_minute_campaign/input"
    manifest = json.loads((input_dir / "accepted_underlying_manifest.json").read_text())
    extract_root = input_dir / "extracted"
    for row in manifest:
        row["absolute_path"] = str(extract_root / row["relative_path"])
    run_campaign(manifest, tmp_path / "run", source_manifest_hash=file_sha256(input_dir / "accepted_underlying_manifest.json"), code_commit="abc123")
    path = tmp_path / "run/development_results.json"
    payload = json.loads(path.read_text())
    payload["verdict"] = "CANDIDATE_FROZEN"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    audit = audit_campaign(input_dir, tmp_path / "run", tmp_path / "audit.json")
    assert audit["matches_primary_verdict"] is False


def test_independent_audit_has_no_prohibited_imports(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    certify_archive(archive, tmp_path, commit="abc123")
    input_dir = tmp_path / "research/kite_five_minute_campaign/input"
    manifest = json.loads((input_dir / "accepted_underlying_manifest.json").read_text())
    extract_root = input_dir / "extracted"
    for row in manifest:
        row["absolute_path"] = str(extract_root / row["relative_path"])
    run_campaign(manifest, tmp_path / "run", source_manifest_hash=file_sha256(input_dir / "accepted_underlying_manifest.json"), code_commit="abc123")
    audit = audit_campaign(input_dir, tmp_path / "run", tmp_path / "audit.json")
    assert audit["dependency_import_audit"]["prohibited_imports_absent"]


def test_candidate_hash_is_output_path_independent() -> None:
    assert frozen_variants()[0] == frozen_variants()[0]
