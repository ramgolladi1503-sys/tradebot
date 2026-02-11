from datetime import datetime, timedelta
import importlib.util
import sys
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
_SCHED_PATH = _ROOT / "scripts" / "scheduler.py"
spec = importlib.util.spec_from_file_location("scheduler", _SCHED_PATH)
assert spec and spec.loader
scheduler = importlib.util.module_from_spec(spec)
sys.modules["scheduler"] = scheduler
spec.loader.exec_module(scheduler)


def test_should_run_once_per_day():
    now = datetime(2026, 2, 11, 9, 5, tzinfo=scheduler.now_ist().tzinfo)
    date_key = scheduler.ist_date_key(now)
    decision = scheduler.should_run_premarket(now, None)
    assert decision.should_run is True
    assert decision.reason in ("on_time", "delayed")

    decision2 = scheduler.should_run_premarket(now, date_key)
    assert decision2.should_run is False
    assert decision2.reason == "already_ran_today"


def test_should_run_delayed_after_window():
    now = datetime(2026, 2, 11, 10, 30, tzinfo=scheduler.now_ist().tzinfo)
    decision = scheduler.should_run_premarket(now, None)
    assert decision.should_run is True
    assert decision.reason == "delayed"
    assert decision.delay_min >= 0
