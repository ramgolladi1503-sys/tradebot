from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "mros"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import mros_autonomous_supervisor as supervisor


def test_clean_authority_checkout_fast_forwards_to_remote_before_cycle(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, ...]] = []

    def fake_git(repo: Path, *args: str, timeout: int = 180, check: bool = True):
        calls.append(tuple(args))
        if args == ("status", "--porcelain"):
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if args == ("merge", "--ff-only", f"origin/{supervisor.AUTHORITY_BRANCH}"):
            return SimpleNamespace(stdout="Already up to date.\n", stderr="", returncode=0)
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(supervisor, "git", fake_git)
    assert supervisor.recover_authority_checkout(tmp_path, tmp_path) is None
    assert ("merge", "--ff-only", f"origin/{supervisor.AUTHORITY_BRANCH}") in calls


def test_dirty_authority_checkout_still_preserves_existing_recovery_path(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, ...]] = []
    status_reads = iter([" M scripts/mros/x.py\n", ""])

    def fake_git(repo: Path, *args: str, timeout: int = 180, check: bool = True):
        calls.append(tuple(args))
        if args == ("status", "--porcelain"):
            return SimpleNamespace(stdout=next(status_reads), stderr="", returncode=0)
        if args == ("rev-parse", "HEAD"):
            return SimpleNamespace(stdout="a" * 40 + "\n", stderr="", returncode=0)
        if args == ("rev-parse", f"origin/{supervisor.AUTHORITY_BRANCH}"):
            return SimpleNamespace(stdout="b" * 40 + "\n", stderr="", returncode=0)
        if args == ("merge-base", "--is-ancestor", "a" * 40, "b" * 40):
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if args[:3] == ("stash", "push", "--include-untracked"):
            return SimpleNamespace(stdout="Saved working directory\n", stderr="", returncode=0)
        if args == ("stash", "list", "-1", "--format=%gd:%H:%s"):
            return SimpleNamespace(stdout="stash@{0}:deadbeef:recovery\n", stderr="", returncode=0)
        if args == ("merge", "--ff-only", f"origin/{supervisor.AUTHORITY_BRANCH}"):
            return SimpleNamespace(stdout="Updating\n", stderr="", returncode=0)
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(supervisor, "git", fake_git)
    supervisor.recover_authority_checkout(tmp_path, tmp_path)
    assert ("merge", "--ff-only", f"origin/{supervisor.AUTHORITY_BRANCH}") in calls
