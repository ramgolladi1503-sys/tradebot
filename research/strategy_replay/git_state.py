from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .common import StrategyReplayError


@dataclass(frozen=True)
class GitExecutionState:
    commit_sha: str
    worktree_clean: bool
    dirty_path_count: int
    dirty_paths: tuple[str, ...]
    repo_root: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_git_execution_state(repo_root: Path | str, *, required_clean: bool = False) -> GitExecutionState:
    root = Path(repo_root).resolve()
    commit_sha = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    status_lines = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain"],
        text=True,
    ).splitlines()
    dirty_paths = tuple(sorted(line[3:] for line in status_lines if len(line) >= 4))
    state = GitExecutionState(
        commit_sha=commit_sha,
        worktree_clean=not dirty_paths,
        dirty_path_count=len(dirty_paths),
        dirty_paths=dirty_paths,
        repo_root=str(root),
    )
    if required_clean and not state.worktree_clean:
        raise StrategyReplayError(f"dirty_worktree_rejected:{state.dirty_path_count}")
    return state
