from __future__ import annotations

from typing import Sequence

from mcp.server.fastmcp import FastMCP

from tools.tradebot_mcp.core import Settings
from tools.tradebot_mcp.safe_git import SafeGitAuditService

mcp = FastMCP(
    "tradebot-git-audit",
    instructions=(
        "Read-only Git evidence for TradeBot worktrees, commit scope and prohibited paths. "
        "No reset, checkout, merge, delete, force-push or ref mutation tools exist."
    ),
    json_response=True,
)
service = SafeGitAuditService(Settings.from_env())


@mcp.tool()
def get_worktree_status() -> dict:
    """Return branch, HEAD and porcelain status for the configured worktree."""
    return service.get_worktree_status()


@mcp.tool()
def list_worktrees() -> dict:
    """List registered Git worktrees using porcelain output."""
    return service.list_worktrees()


@mcp.tool()
def get_branch_head(ref: str = "HEAD") -> dict:
    """Resolve one validated Git ref to a commit SHA."""
    return service.get_branch_head(ref)


@mcp.tool()
def get_changed_files(base: str | None = None, head: str = "HEAD") -> dict:
    """List worktree changes or changed paths between validated refs."""
    return service.get_changed_files(base, head)


@mcp.tool()
def scan_prohibited_paths(
    base: str,
    head: str = "HEAD",
    prohibited_prefixes: Sequence[str] | None = None,
) -> dict:
    """Fail when a diff touches configured production or secret-bearing prefixes."""
    return service.scan_prohibited_paths(base, head, prohibited_prefixes)


@mcp.tool()
def verify_commit_scope(
    base: str,
    head: str,
    allowed_prefixes: Sequence[str],
    prohibited_prefixes: Sequence[str] | None = None,
) -> dict:
    """Verify that every changed path is owned by the task and not prohibited."""
    return service.verify_commit_scope(base, head, allowed_prefixes, prohibited_prefixes)


@mcp.tool()
def check_worktree_clean() -> dict:
    """Return whether the configured worktree has no tracked or untracked changes."""
    return service.check_worktree_clean()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
