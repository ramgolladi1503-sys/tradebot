"""Unit tests for Track C: Single Scheduler Authority & Timezone Mapping."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import pytest

from scripts.scheduler import BACKGROUND_SCRIPTS


def test_antigravity_sidecar_cron_mapping_utc_to_ist():
    """Verify 15 3 * * 1-5 maps deterministically to 08:45 IST on weekdays."""
    sidecar_path = Path.home() / ".gemini" / "config" / "sidecars" / "tradebot_mros_morning_observer" / "sidecar.json"
    if sidecar_path.is_file():
        cfg = json.loads(sidecar_path.read_text(encoding="utf-8"))
        cron_expr = cfg["args"][0]
        assert cron_expr == "15 3 * * 1-5", f"Expected UTC cron 15 3 * * 1-5, got {cron_expr}"

    ist_tz = ZoneInfo("Asia/Kolkata")
    # Test multiple future Monday-Friday dates
    test_dates = [
        datetime(2026, 9, 18, 8, 45, 0, tzinfo=ist_tz),  # Friday
        datetime(2026, 9, 21, 8, 45, 0, tzinfo=ist_tz),  # Monday
        datetime(2026, 9, 22, 8, 45, 0, tzinfo=ist_tz),  # Tuesday
        datetime(2026, 9, 23, 8, 45, 0, tzinfo=ist_tz),  # Wednesday
        datetime(2026, 9, 24, 8, 45, 0, tzinfo=ist_tz),  # Thursday
        datetime(2026, 9, 25, 8, 45, 0, tzinfo=ist_tz),  # Friday
        datetime(2026, 10, 1, 8, 45, 0, tzinfo=ist_tz),  # Thursday
        datetime(2026, 12, 1, 8, 45, 0, tzinfo=ist_tz),  # Tuesday
    ]

    for dt_ist in test_dates:
        # Weekdays only (0=Mon, 4=Fri)
        assert dt_ist.weekday() < 5, f"{dt_ist} is not a weekday"
        dt_utc = dt_ist.astimezone(timezone.utc)
        assert dt_utc.hour == 3, f"UTC hour mismatch for {dt_ist}: expected 3, got {dt_utc.hour}"
        assert dt_utc.minute == 15, f"UTC minute mismatch for {dt_ist}: expected 15, got {dt_utc.minute}"


def test_legacy_scheduler_does_not_spawn_competing_live_collector():
    """Verify scripts/scheduler.py does not spawn tick_data_collector.py independently."""
    assert "scripts/tick_data_collector.py" not in BACKGROUND_SCRIPTS, (
        "scripts/scheduler.py must not independently launch tick_data_collector.py; "
        "it must be governed exclusively by run_governed_morning_observer_v1.py"
    )


def test_one_schedule_authority_invariant():
    """Ensure the sidecar triggers the governed morning observer entrypoint without SHA hardcoding."""
    sidecar_path = Path.home() / ".gemini" / "config" / "sidecars" / "tradebot_mros_morning_observer" / "sidecar.json"
    if not sidecar_path.is_file():
        pytest.skip("Sidecar config not present in test environment")

    cfg = json.loads(sidecar_path.read_text(encoding="utf-8"))
    cmd_args = " ".join(cfg.get("args", []))
    assert "scripts/run_governed_morning_observer_v1.py" in cmd_args
    # Must dynamically resolve SHA from ReleaseStore, no hardcoded SHA
    assert "--expected-sha" not in cmd_args
