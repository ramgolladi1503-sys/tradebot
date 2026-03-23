from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_prompts.sh"


def _run_runner(*args: str, dry_run: bool = False) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if dry_run:
        env["VERIFY_PROMPTS_DRY_RUN"] = "1"
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_verify_prompts_help_and_shell_syntax() -> None:
    syntax = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    result = _run_runner("help")
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "core" in result.stdout

    mode = SCRIPT.stat().st_mode
    assert mode & stat.S_IXUSR


def test_verify_prompts_range_dispatch_supports_dry_run() -> None:
    result = _run_runner("1-2", dry_run=True)
    assert result.returncode == 0, result.stderr
    assert "1) rg observability funnel" in result.stdout
    assert "2) rg main.py global suppressor fix" in result.stdout
    assert "[dry-run]" in result.stdout


def test_verify_prompts_invalid_target_fails_with_usage() -> None:
    result = _run_runner("bad-target", dry_run=True)
    assert result.returncode == 1
    assert "Usage:" in result.stdout
