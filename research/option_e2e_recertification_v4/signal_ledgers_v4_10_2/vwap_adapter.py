from __future__ import annotations

from pathlib import Path


def build_vwap_adapter(_repo_root: Path) -> dict[str, object]:
    """No research adapter is frozen yet; direct strategy execution is not enabled."""

    return {
        "path": None,
        "hash": None,
        "status": "NO_REVIEWED_RESEARCH_ADAPTER",
    }
