#!/usr/bin/env python3
"""Compatibility entrypoint for the primitive-first PR #905 proof generator."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from pr905_proof_v2 import generate_proof, main  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
