from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "research" / "hypothesis_factory" / "run_raj_arora_external_seeded_proxy_v1_development.py"
spec = importlib.util.spec_from_file_location("raj_proxy_runner", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

IST = ZoneInfo("Asia/Kolkata")


def _bars(rows):
    start = datetime(2026, 1, 5, 9, 15, tzinfo=IST)
    return [
        {
            "timestamp": start + timedelta(minutes=5 * i),
            "session": "2026-01-05",
            "open": o,
            "high": h,
            "low": l,
            "close": c,
        }
        for i, (o, h, l, c) in enumerate(rows)
    ]


def test_opening_range_breakout_retest_requires_separate_continuation_bar():
    bars = _bars([
        (100, 102, 99, 101),
        (101, 103, 100, 102),
        (102, 103, 101, 102.5),
        (102.5, 104.5, 102.4, 104),
        (104, 104.2, 102.8, 103.2),
        (103.2, 105.2, 103.1, 105),
        (105, 106, 104.5, 105.5),
    ])
    cfg = {
        "or_bars": 3,
        "breakout_buffer_bps": 0,
        "retest_max_bars": 3,
        "continuation_max_bars": 2,
    }
    assert mod.first_or_retest_continuation(bars, cfg) == (5, 1)


def test_failed_breakout_reverses_only_after_later_close_returns_inside_range():
    bars = _bars([
        (100, 102, 99, 101),
        (101, 103, 100, 102),
        (102, 103, 101, 102.5),
        (102.5, 104.5, 102.4, 104),
        (104, 104.1, 102.0, 102.5),
        (102.5, 103, 101.5, 102),
    ])
    cfg = {"or_bars": 3, "breakout_buffer_bps": 0, "failure_max_bars": 2}
    assert mod.first_or_failed_breakout(bars, cfg) == (4, -1)


def test_opening_drive_pullback_resumption_is_ordered_and_causal():
    bars = _bars([
        (100, 101.5, 99.8, 101),
        (101, 102.5, 100.8, 102),
        (102, 103.2, 101.8, 103),
        (103, 103.1, 101.5, 102),
        (102, 103.0, 101.8, 102.8),
        (102.8, 104, 102.6, 103.8),
        (103.8, 104.2, 103.5, 104),
    ])
    cfg = {
        "drive_bars": 3,
        "drive_min_bps": 25,
        "min_retrace_fraction": 0.25,
        "max_retrace_fraction": 0.65,
        "pullback_max_bars": 4,
        "resumption_max_bars": 2,
    }
    assert mod.first_opening_drive_pullback_resumption(bars, cfg) == (5, 1)


def test_opening_prefix_fails_closed_when_session_does_not_start_at_0915():
    bars = _bars([
        (100, 101, 99, 100.5),
        (100.5, 101, 100, 100.8),
        (100.8, 101.2, 100.4, 101),
        (101, 102, 100.9, 101.8),
    ])
    bars[0]["timestamp"] = bars[0]["timestamp"] + timedelta(minutes=5)
    assert not mod.valid_opening_prefix(bars, 3)
