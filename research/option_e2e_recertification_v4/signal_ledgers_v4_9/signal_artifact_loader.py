from __future__ import annotations

from pathlib import Path


def load_signal_artifacts(repo_root: Path) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    for path in repo_root.rglob("*.jsonl"):
        if "runtime" not in path.parts:
            continue
        artifacts.append({"path": str(path), "kind": "jsonl"})
    for path in repo_root.rglob("*.csv"):
        if "runtime" not in path.parts:
            continue
        artifacts.append({"path": str(path), "kind": "csv"})
    for path in repo_root.rglob("*.parquet"):
        if "runtime" not in path.parts:
            continue
        artifacts.append({"path": str(path), "kind": "parquet"})
    return artifacts
