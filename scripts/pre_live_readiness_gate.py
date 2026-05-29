#!/usr/bin/env python
"""CLI wrapper for the pre-market LIVE readiness gate."""

from __future__ import annotations

from core.pre_live_readiness_gate import *  # noqa: F401,F403
from core.pre_live_readiness_gate import main


if __name__ == "__main__":
    raise SystemExit(main())
