from __future__ import annotations

from pathlib import Path


def discover_historical_sources(repo_root: Path) -> dict[str, tuple[str, ...]]:
    searched = [
        repo_root / "research" / "option_e2e_recertification_v4" / "inventory",
        repo_root / "research" / "option_e2e_recertification_v4" / "inventory_v4_1",
        repo_root / "docs" / "agent_reviews",
        repo_root / "strategies",
        repo_root / "runtime" / "strategy_validation",
    ]
    return {
        "searched_roots": tuple(str(path) for path in searched if path.exists()),
        "discovery_command": "git log + inventory manifests + strategy source scan",
    }
