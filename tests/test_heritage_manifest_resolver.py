"""
Unit and regression tests for HeritageManifestResolver (ARCH-01 Stage 2 GSD verification).

Tests:
1. Calendar backward scan over normal weekends (Monday -> Friday).
2. Calendar backward scan over NSE exchange holidays (steps over mid-week holidays).
3. Lookback exceeded threshold fails closed (returns NO_PREDECESSOR_FOUND).
4. Verified valid manifest returns RESOLVED with matching path and computed sha256.
5. Tampered manifest payload fails closed (MANIFEST_VERIFICATION_FAILED).
6. Corrupt JSON fails closed (CORRUPT_MANIFEST).
7. Nonexistent session folder fails closed (MANIFEST_NOT_FOUND).
"""

import datetime as dt
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.heritage_manifest_resolver import (
    HeritageManifestResolution,
    HeritageManifestResolver,
    ResolutionStatus,
)


def _create_sample_manifest(session_date: str) -> dict:
    return {
        "manifest_version": "v1",
        "session_date": session_date,
        "exchange": "NSE",
        "market": "FNO",
        "nodes": [
            {
                "symbol": "NIFTY",
                "instrument_token": 256265,
                "close_price": 24850.5,
                "vwap": 24820.1,
                "volume": 12500000,
            }
        ],
        "edges": [],
        "metadata": {"sealed": True, "created_at": f"{session_date}T16:00:00+05:30"},
    }


def test_resolver_calendar_backward_scan_weekend():
    # 2026-10-19 is a Monday. Predecessor should be Friday 2026-10-16.
    pred = HeritageManifestResolver.find_predecessor_date("2026-10-19")
    assert pred == dt.date(2026, 10, 16)


def test_resolver_calendar_backward_scan_midweek_holiday():
    # 2026-01-26 is Republic Day (official NSE holiday).
    # If target is Tuesday 2026-01-27, Monday 2026-01-26 is holiday, so predecessor is Friday 2026-01-23.
    pred = HeritageManifestResolver.find_predecessor_date("2026-01-27")
    assert pred == dt.date(2026, 1, 23)


def test_resolver_lookback_exceeded_fails_closed():
    # If lookback is restricted to 2 days on a Monday, it cannot reach Friday.
    pred = HeritageManifestResolver.find_predecessor_date("2026-10-19", max_lookback_days=2)
    assert pred is None

    res = HeritageManifestResolver.resolve(
        target_date="2026-10-19",
        search_roots=[],
        max_lookback_days=2,
    )
    assert res.status == ResolutionStatus.NO_PREDECESSOR_FOUND
    assert res.manifest_path is None
    assert res.read_only is True
    assert res.is_order_action is False


def test_resolver_missing_manifest_returns_not_found(tmp_path: Path):
    res = HeritageManifestResolver.resolve(
        target_date="2026-10-15",
        search_roots=[tmp_path],
    )
    assert res.status == ResolutionStatus.MANIFEST_NOT_FOUND
    assert res.predecessor_date == "2026-10-14"
    assert res.manifest_path is None


def test_resolver_corrupt_manifest_fails_closed(tmp_path: Path):
    session_dir = tmp_path / "session_2026-10-14"
    session_dir.mkdir(parents=True)
    manifest_file = session_dir / "heritage_manifest.json"
    manifest_file.write_text("{ incomplete json ... corrupt ")

    res = HeritageManifestResolver.resolve(
        target_date="2026-10-15",
        search_roots=[tmp_path],
    )
    assert res.status == ResolutionStatus.CORRUPT_MANIFEST
    assert res.manifest_path == manifest_file


def test_resolver_verified_manifest_success(tmp_path: Path):
    session_dir = tmp_path / "session_2026-10-14"
    session_dir.mkdir(parents=True)
    manifest_file = session_dir / "heritage_manifest.json"
    content = json.dumps(_create_sample_manifest("2026-10-14"), indent=2)
    manifest_file.write_text(content)
    expected_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

    mock_report = {
        "verdict": "PASS",
        "manifest_sha256": expected_sha256,
        "session_date": "2026-10-14",
        "errors": [],
    }

    with patch(
        "core.heritage_manifest_resolver.verify_market_heritage_manifest",
        return_value=mock_report,
    ):
        res = HeritageManifestResolver.resolve(
            target_date="2026-10-15",
            search_roots=[tmp_path],
        )
        assert res.status == ResolutionStatus.RESOLVED
        assert res.manifest_path == manifest_file.resolve()
        assert res.manifest_sha256 == expected_sha256
        assert res.predecessor_date == "2026-10-14"
        assert res.read_only is True
        assert res.broker_api_called is False


def test_resolver_tampered_manifest_fails_closed(tmp_path: Path):
    session_dir = tmp_path / "session_2026-10-14"
    session_dir.mkdir(parents=True)
    manifest_file = session_dir / "heritage_manifest.json"
    content = json.dumps(_create_sample_manifest("2026-10-14"), indent=2)
    manifest_file.write_text(content)

    mock_report = {
        "verdict": "FAIL",
        "manifest_sha256": "fake_sha256",
        "session_date": "2026-10-14",
        "errors": ["SIGNATURE_INVALID", "NODE_PRICE_DISCREPANCY"],
    }

    with patch(
        "core.heritage_manifest_resolver.verify_market_heritage_manifest",
        return_value=mock_report,
    ):
        res = HeritageManifestResolver.resolve(
            target_date="2026-10-15",
            search_roots=[tmp_path],
        )
        assert res.status == ResolutionStatus.MANIFEST_VERIFICATION_FAILED
        assert res.manifest_path == manifest_file
        assert "SIGNATURE_INVALID" in str(res.error_message)
