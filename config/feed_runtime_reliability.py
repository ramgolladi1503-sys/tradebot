"""Configuration owned by the MROS runtime reliability repair.

Keep these settings separate from ``config.config`` because that module is
cryptographically pinned by the regime immutability audit. Environment names
and defaults remain stable for deployment compatibility.
"""

from __future__ import annotations

import os


FEED_RUNTIME_SNAPSHOT_QUEUE_MAXSIZE = int(
    os.getenv("FEED_RUNTIME_SNAPSHOT_QUEUE_MAXSIZE", "2048")
)
FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC = float(
    os.getenv("FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC", "0.5")
)
FEED_RECOVERY_MAX_GAP_SEC = float(os.getenv("FEED_RECOVERY_MAX_GAP_SEC", "3.0"))
FEED_RECOVERY_HEALTH_WINDOW_SEC = float(
    os.getenv("FEED_RECOVERY_HEALTH_WINDOW_SEC", "2.0")
)
MEG_COMPLETION_GRACE_MS = int(os.getenv("MEG_COMPLETION_GRACE_MS", "800"))
MEG_MAX_DECISION_FRESHNESS_SEC = float(
    os.getenv("MEG_MAX_DECISION_FRESHNESS_SEC", "15.0")
)
DEPTH_CAPTURE_MODE = "SAMPLED_DEPTH"
