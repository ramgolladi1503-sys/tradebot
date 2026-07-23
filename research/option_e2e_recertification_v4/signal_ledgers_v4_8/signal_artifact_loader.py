from __future__ import annotations

from pathlib import Path


def load_signal_artifacts(repo_root: Path) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    for path in (repo_root / "runtime" / "strategy_validation").rglob("*.json"):
        if path.is_file():
            artifacts.append({"path": str(path), "kind": "json_artifact"})
    return artifacts
