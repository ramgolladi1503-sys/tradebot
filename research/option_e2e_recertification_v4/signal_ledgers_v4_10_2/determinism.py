from __future__ import annotations

from pathlib import Path


def build_determinism_fingerprint(repo_root: Path) -> dict[str, str]:
    return {"repo_root": str(repo_root), "fingerprint": "v4_10_2_deterministic_blocked"}

