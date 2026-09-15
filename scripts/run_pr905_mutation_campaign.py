#!/usr/bin/env python3
"""Compatibility entrypoint for the primitive PR #905 mutation campaign."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pr905_mutation_v2 import main, run_mutation_campaign  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
