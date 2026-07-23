from __future__ import annotations

from pathlib import Path


def discover_historical_sources(repo_root: Path) -> dict[str, tuple[str, ...]]:
    return {
        "searched_roots": (
            str(repo_root / "runtime" / "upstox_instruments"),
            str(repo_root / "runtime" / "upstox_candidate_replay"),
            str(repo_root / "runtime" / "market_data" / "upstox"),
        ),
        "discovery_command": "repo-local discovery only; no broker/live access",
    }
