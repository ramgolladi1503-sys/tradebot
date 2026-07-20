#!/usr/bin/env python3
"""Generate ORB fidelity audit artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.opening_range_retest_fidelity_audit.evaluator import write_all  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(write_all(), sort_keys=True, indent=2))
