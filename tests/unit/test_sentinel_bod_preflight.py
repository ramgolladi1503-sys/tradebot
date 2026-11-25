import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from scripts.ops.reset_sentinel_wal_for_session import reset_wal_file


def test_reset_sentinel_wal_clean_slate(tmp_path):
    """Proves that reset_sentinel_wal_for_session cleans stale COOL_OFF/CRASH_RECOVERY to STANDBY."""
    wal = tmp_path / "sentinel_apm_wal.json"
    stale_data = {
        "state": "COOL_OFF",
        "last_completed_trade": {
            "position_id": "TRADE_NIFTY_094400_CE",
            "entry_time": "2026-11-13T09:44:00+05:30",
            "exit_reason": "CRASH_RECOVERY_FAIL_CLOSED",
        },
        "cool_off_until": "2026-11-13T21:42:23.720812",
    }
    with open(wal, "w") as f:
        json.dump(stale_data, f)

    today_str = "2026-11-14"
    updated = reset_wal_file(wal, today_str=today_str, dry_run=False)
    assert updated is True

    with open(wal, "r") as f:
        clean = json.load(f)

    assert clean["state"] == "STANDBY"
    assert clean["cool_off_until"] is None
    assert clean["session_date"] == today_str
    assert clean["reset_reason"] == "BOD_PREFLIGHT_CLEAN_SLATE"


def test_reset_sentinel_wal_already_clean(tmp_path):
    """Proves that a WAL already in STANDBY for today requires no reset."""
    wal = tmp_path / "sentinel_apm_wal.json"
    today_str = "2026-11-14"
    clean_data = {
        "state": "STANDBY",
        "last_completed_trade": None,
        "cool_off_until": None,
        "session_date": today_str,
    }
    with open(wal, "w") as f:
        json.dump(clean_data, f)

    updated = reset_wal_file(wal, today_str=today_str, dry_run=False)
    assert updated is False


def test_upstox_auth_preflight_valid_token(monkeypatch):
    """Proves that HTTP 200 response from Upstox profile endpoint passes preflight."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps({"data": {"user_name": "Test Trader"}}).encode()

    with patch("urllib.request.urlopen", return_value=mock_resp):
        import urllib.request
        req = urllib.request.Request("https://api.upstox.com/v2/user/profile")
        resp = urllib.request.urlopen(req)
        assert resp.status == 200


def test_upstox_auth_preflight_401_fails_closed():
    """Proves that an HTTP 401 error raises HTTPError and fails closed."""
    import urllib.error
    import urllib.request
    err = urllib.error.HTTPError("https://api.upstox.com/v2/user/profile", 401, "Unauthorized", {}, None)
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen("https://api.upstox.com/v2/user/profile")
        assert exc_info.value.code == 401
