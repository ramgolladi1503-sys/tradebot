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


def test_t1_prerequisites_generated_manifest_verified_by_oracle(mock_snapshot_file, tmp_path):
    manifest_path = tmp_path / "t1_prerequisites.json"
    doc = compute_manifest(
        source_snapshot_path=mock_snapshot_file,
        source_session_date="2026-09-22",
        target_session_date="2026-09-23",
    )
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    result = verify_manifest(manifest_path)
    assert result["independent_oracle_verdict"] == "PASS"
    assert result["spot_close_matches"] is True
    assert result["payload_sha_verified"] is True
    assert result["t1_close_authority_status"] == "BLOCKED_SOURCE_AUTHORITY"
    assert result["sma200_authority_status"] == "BLOCKED_SOURCE_AUTHORITY"


def test_oracle_fails_on_tampered_payload_hash(mock_snapshot_file, tmp_path):
    manifest_path = tmp_path / "t1_prerequisites.json"
    doc = compute_manifest(
        source_snapshot_path=mock_snapshot_file,
        source_session_date="2026-09-22",
        target_session_date="2026-09-23",
    )
    doc["payload_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="Payload SHA-256 mismatch"):
        verify_manifest(manifest_path)


def test_oracle_fails_on_tampered_spot_close(mock_snapshot_file, tmp_path):
    manifest_path = tmp_path / "t1_prerequisites.json"
    doc = compute_manifest(
        source_snapshot_path=mock_snapshot_file,
        source_session_date="2026-09-22",
        target_session_date="2026-09-23",
    )
    doc["overnight_prev_daily_close"] = 99999.0
    manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="Spot close mismatch"):
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

    with pytest.raises(ValueError, match="opening_drive_prev_close_1529 must be null"):
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

    with pytest.raises(ValueError, match="overnight_prev_sma200 must be null"):
        verify_manifest(manifest_path)
