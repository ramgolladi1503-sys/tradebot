from __future__ import annotations

import subprocess
from pathlib import Path


LANE_DISCOVERY = {
    "VWAP_RECLAIM": ("VWAP_RECLAIM", "vwap_reclaim", "strategies/movement/vwap_reclaim.py"),
    "OPENING_RANGE_BREAKOUT": ("OPENING_RANGE_BREAKOUT", "opening_range_breakout", "strategies/movement/opening_range_breakout.py"),
    "OPENING_STATE_MOMENTUM": ("OPENING_STATE_MOMENTUM", "opening-state", "research/option_e2e_recertification_v4/inventory_v4_1/build_inventory_v4_1.py"),
}


def _run(repo_root: Path, command: list[str]) -> dict[str, object]:
    try:
        proc = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, timeout=6, check=False)
        return {
            "command": " ".join(command),
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "exit_code": 124,
            "stdout": exc.output or "",
            "stderr": exc.stderr or "timeout",
        }


def run_git_discovery(repo_root: Path) -> dict[str, object]:
    commands = [_run(repo_root, ["git", "worktree", "list", "--porcelain"])]
    for lane, tokens in LANE_DISCOVERY.items():
        _, alias, alt_alias = tokens
        path = tokens[2]
        commands.extend(
            [
                _run(repo_root, ["git", "log", "--all", f"-S{lane}", "--oneline"]),
                _run(repo_root, ["git", "log", "--all", f"-S{alias}", "--oneline"]),
                _run(repo_root, ["git", "log", "--all", "--name-only", "--", path]),
                _run(repo_root, ["git", "rev-list", "--all", "--", path]),
                _run(repo_root, ["git", "ls-tree", "-r", "HEAD", "--", path]),
                _run(repo_root, ["git", "log", "--all", f"-S{alt_alias}", "--oneline"]),
            ]
        )
    return {"commands": commands}
