from pathlib import Path
import json
import runpy

from core.time_utils import normalize_epoch_seconds


def test_normalize_epoch_seconds_handles_ms_and_us():
    sec = 1770715482.335
    ms = sec * 1000.0
    us = sec * 1_000_000.0

    assert abs(normalize_epoch_seconds(sec) - sec) < 1e-6
    assert abs(normalize_epoch_seconds(ms) - sec) < 1e-6
    assert abs(normalize_epoch_seconds(us) - sec) < 1e-6


def test_pilot_feed_check_respects_market_open_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    checklist = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "run_pilot_checklist.py"))
    check_feed = checklist["_check_feed"]

    from core import freshness_sla
    payload = {
        "market_open": False,
        "ltp": {"age_sec": 17070.0},
        "depth": {"age_sec": 17070.0},
    }
    monkeypatch.setattr(freshness_sla, "get_freshness_status", lambda force=False: payload)
    ok_closed, reasons_closed = check_feed()
    assert ok_closed is True
    assert reasons_closed == []

    payload["market_open"] = True
    ok_open, reasons_open = check_feed()
    assert ok_open is False
    assert "depth_feed_stale" in reasons_open
