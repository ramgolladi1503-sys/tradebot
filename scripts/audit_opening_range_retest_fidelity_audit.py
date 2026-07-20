#!/usr/bin/env python3
"""Audit generated ORB fidelity artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.opening_range_retest_fidelity_audit.artifact_audit import audit_artifacts  # noqa: E402


if __name__ == "__main__":
    result = audit_artifacts()
    print(json.dumps(result, sort_keys=True, indent=2))
    raise SystemExit(0 if result["status"] == "READY" else 1)
