from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.structural_edge_discovery_v3.engine import CampaignConfig, run_campaign


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run research-only structural edge discovery V3.")
    parser.add_argument("--output-dir", type=Path, default=Path("research/structural_edge_discovery_v3"))
    parser.add_argument("--max-sessions", type=int, default=140)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    cfg = CampaignConfig(
        repo_path=repo,
        output_dir=(repo / args.output_dir).resolve() if not args.output_dir.is_absolute() else args.output_dir,
        source_worktree=repo,
        branch=_git(["rev-parse", "--abbrev-ref", "HEAD"], repo),
        base_branch="data/combined-upstox-20260714",
        base_commit=_git(["rev-parse", "HEAD"], repo),
        previous_head=_git(["rev-parse", "HEAD"], repo),
        max_sessions=args.max_sessions,
    )
    verdict = run_campaign(cfg)
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
