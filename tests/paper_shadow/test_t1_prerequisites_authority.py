#!/usr/bin/env python3
"""Adversarial and Negative Control Test Suite for T-1 Prerequisites Provenance and Oracle."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from scripts.generate_t1_prerequisites import compute_manifest
from scripts.verify_t1_prerequisites_oracle import verify_manifest


def test_t1_prerequisites_generated_manifest_verified_by_oracle():
    manifest_path = Path("runtime/preflight/t1_prerequisites_2026-09-23.json")
    assert manifest_path.is_file()
    result = verify_manifest(manifest_path)
    assert result["independent_oracle_verdict"] == "PASS"
    assert result["spot_close_matches"] is True
    assert result["payload_sha_verified"] is True
    assert result["t1_close_authority_status"] == "BLOCKED_SOURCE_AUTHORITY"
    assert result["sma200_authority_status"] == "BLOCKED_SOURCE_AUTHORITY"


def test_oracle_fails_on_tampered_payload_hash(tmp_path):
    manifest_path = Path("runtime/preflight/t1_prerequisites_2026-09-23.json")
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["payload_sha256"] = "0" * 64
    tampered_file = tmp_path / "tampered_manifest.json"
    tampered_file.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="Payload SHA-256 mismatch"):
        verify_manifest(tampered_file)


def test_oracle_fails_on_tampered_spot_close(tmp_path):
    manifest_path = Path("runtime/preflight/t1_prerequisites_2026-09-23.json")
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["overnight_prev_daily_close"] = 99999.0
    tampered_file = tmp_path / "tampered_manifest.json"
    tampered_file.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="Spot close mismatch"):
        verify_manifest(tampered_file)


def test_oracle_fails_if_futures_close_is_fabricated_without_dataset(tmp_path):
    manifest_path = Path("runtime/preflight/t1_prerequisites_2026-09-23.json")
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["opening_drive_prev_close_1529"] = 23329.0
    tampered_file = tmp_path / "tampered_manifest.json"
    tampered_file.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="opening_drive_prev_close_1529 must be null"):
        verify_manifest(tampered_file)


def test_oracle_fails_if_sma200_is_fabricated_without_dataset(tmp_path):
    manifest_path = Path("runtime/preflight/t1_prerequisites_2026-09-23.json")
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    doc["overnight_prev_sma200"] = 22450.0
    tampered_file = tmp_path / "tampered_manifest.json"
    tampered_file.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="overnight_prev_sma200 must be null"):
        verify_manifest(tampered_file)
