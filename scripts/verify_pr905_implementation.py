#!/usr/bin/env python3
"""Compatibility entrypoint for the independent primitive PR #905 verifier."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pr905_verifier_v2 import main, verify_pr905_codebase, verify_pr905_evidence  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
