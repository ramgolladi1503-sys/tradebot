#!/usr/bin/env python3
"""Adversarial and Negative Control Test Suite for T-1 Prerequisites Provenance and Oracle."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from scripts.generate_t1_prerequisites import compute_manifest
from scripts.verify_t1_prerequisites_oracle import verify_manifest


@pytest.fixture
def mock_snapshot_file(tmp_path) -> Path:
    snap_data = {
        "generated_at": "2026-09-22T09:59:59.949130Z",
        "payload": {
            "symbols": {
                "NIFTY": {
                    "ltp": 23329.0,
                    "quote_truth": {"ltp": 23329.0}
                }
            }
        }
    }
    path = tmp_path / "market_snapshot.json"
    path.write_text(json.dumps(snap_data), encoding="utf-8")
    return path


def test_legacy_inventory_preserves_source_hashes_but_blocks_snapshot_ltp(mock_snapshot_file, tmp_path):
    manifest_path = tmp_path / "t1_prerequisites.json"
    doc = compute_manifest(
        source_snapshot_path=mock_snapshot_file,
        source_session_date="2026-09-22",
        target_session_date="2026-09-23",
        contract_key="NIFTY26SEPFUT",
        target_expiry="2026-09-24",
    )
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    result = verify_manifest(manifest_path)
    assert result["independent_oracle_verdict"] == "PASS_BLOCKED_INVENTORY_ONLY"
    assert result["data_authority"] == "BLOCKED_SOURCE_AUTHORITY"
    assert result["payload_sha_verified"] is True
    assert doc["overnight_prev_daily_close"] is None
    assert doc["overnight_prev_daily_close_status"] == "BLOCKED_SOURCE_AUTHORITY"
    assert doc["opening_drive_prev_close_1529"] is None
    assert doc["overnight_prev_sma200"] is None
    assert doc["opening_drive_prev_contract_key"] is None
    assert doc["untrusted_contract_key_hint"] == "NIFTY26SEPFUT"
    assert doc["untrusted_target_expiry_hint"] == "2026-09-24"


def test_oracle_fails_on_tampered_payload_hash(mock_snapshot_file, tmp_path):
    manifest_path = tmp_path / "t1_prerequisites.json"
    doc = compute_manifest(
        source_snapshot_path=mock_snapshot_file,
        source_session_date="2026-09-22",
        target_session_date="2026-09-23",
    )
    doc["payload_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="Inventory payload SHA-256 mismatch"):
        verify_manifest(manifest_path)


def test_oracle_rejects_spot_ltp_promoted_to_previous_daily_close(mock_snapshot_file, tmp_path):
    manifest_path = tmp_path / "t1_prerequisites.json"
    doc = compute_manifest(
        source_snapshot_path=mock_snapshot_file,
        source_session_date="2026-09-22",
        target_session_date="2026-09-23",
    )
    doc["overnight_prev_daily_close"] = 99999.0
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be promoted by a legacy inventory"):
        verify_manifest(manifest_path)


def test_oracle_fails_if_futures_close_is_fabricated_without_dataset(mock_snapshot_file, tmp_path):
    manifest_path = tmp_path / "t1_prerequisites.json"
    doc = compute_manifest(
        source_snapshot_path=mock_snapshot_file,
        source_session_date="2026-09-22",
        target_session_date="2026-09-23",
    )
    doc["opening_drive_prev_close_1529"] = 23329.0
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be promoted by a legacy inventory"):
        verify_manifest(manifest_path)


def test_oracle_fails_if_sma200_is_fabricated_without_dataset(mock_snapshot_file, tmp_path):
    manifest_path = tmp_path / "t1_prerequisites.json"
    doc = compute_manifest(
        source_snapshot_path=mock_snapshot_file,
        source_session_date="2026-09-22",
        target_session_date="2026-09-23",
    )
    doc["overnight_prev_sma200"] = 22450.0
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="cannot be promoted by a legacy inventory"):
        verify_manifest(manifest_path)


def test_generator_rejects_noncausal_session_date_order(mock_snapshot_file):
    with pytest.raises(ValueError, match="SOURCE_SESSION_MUST_PRECEDE_TARGET_SESSION"):
        compute_manifest(
            source_snapshot_path=mock_snapshot_file,
            source_session_date="2026-09-23",
            target_session_date="2026-09-22",
        )
