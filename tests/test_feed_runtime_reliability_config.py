from __future__ import annotations

import os
import subprocess
import sys


def test_reliability_settings_preserve_environment_names_and_defaults() -> None:
    code = (
        "from config import feed_runtime_reliability as c; "
        "assert c.FEED_RUNTIME_SNAPSHOT_QUEUE_MAXSIZE == 2048; "
        "assert c.FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC == 0.5; "
        "assert c.FEED_RECOVERY_MAX_GAP_SEC == 3.0; "
        "assert c.FEED_RECOVERY_HEALTH_WINDOW_SEC == 2.0; "
        "assert c.MEG_COMPLETION_GRACE_MS == 800; "
        "assert c.MEG_MAX_DECISION_FRESHNESS_SEC == 15.0; "
        "assert c.DEPTH_CAPTURE_MODE == 'SAMPLED_DEPTH'"
    )
    env = os.environ.copy()
    for key in (
        "FEED_RUNTIME_SNAPSHOT_QUEUE_MAXSIZE",
        "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC",
        "FEED_RECOVERY_MAX_GAP_SEC",
        "FEED_RECOVERY_HEALTH_WINDOW_SEC",
        "MEG_COMPLETION_GRACE_MS",
        "MEG_MAX_DECISION_FRESHNESS_SEC",
    ):
        env.pop(key, None)
    subprocess.run([sys.executable, "-c", code], check=True, env=env)


def test_reliability_settings_keep_existing_environment_overrides() -> None:
    code = (
        "from config import feed_runtime_reliability as c; "
        "assert c.FEED_RUNTIME_SNAPSHOT_QUEUE_MAXSIZE == 17; "
        "assert c.FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC == 1.25; "
        "assert c.FEED_RECOVERY_MAX_GAP_SEC == 4.5; "
        "assert c.FEED_RECOVERY_HEALTH_WINDOW_SEC == 3.5; "
        "assert c.MEG_COMPLETION_GRACE_MS == 125; "
        "assert c.MEG_MAX_DECISION_FRESHNESS_SEC == 7.5"
    )
    env = os.environ.copy()
    env.update(
        {
            "FEED_RUNTIME_SNAPSHOT_QUEUE_MAXSIZE": "17",
            "FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC": "1.25",
            "FEED_RECOVERY_MAX_GAP_SEC": "4.5",
            "FEED_RECOVERY_HEALTH_WINDOW_SEC": "3.5",
            "MEG_COMPLETION_GRACE_MS": "125",
            "MEG_MAX_DECISION_FRESHNESS_SEC": "7.5",
        }
    )
    subprocess.run([sys.executable, "-c", code], check=True, env=env)
