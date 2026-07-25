from __future__ import annotations

import subprocess
from pathlib import Path


def run_git_discovery(repo_root: Path) -> dict[str, object]:
    commands = [
        ["git", "branch", "--all"],
        ["git", "rev-list", "--all"],
        ["git", "log", "--all", "--name-only", "--", "strategies", "research", "runtime", "docs"],
        ["git", "log", "--all", "-S", "VWAP_RECLAIM", "--oneline"],
    ]
    results = []
    for cmd in commands:
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, timeout=60, check=False)
        results.append({"command": " ".join(cmd), "exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
    return {"commands": results}
