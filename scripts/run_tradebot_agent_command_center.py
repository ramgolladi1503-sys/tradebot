#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.agents.command_center import run_agent_command_center


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Tradebot Agent Command Center.")
    parser.add_argument("--runtime-dir", default=".runtime")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--session-dir", default=None)
    parser.add_argument("--out-dir", default=str(Path(".runtime") / "agent_reports"))
    parser.add_argument("--tail-lines", type=int, default=5000)
    parser.add_argument("--agents", nargs="*", default=["all"])
    parser.add_argument("--format", choices=("json", "markdown", "both"), default="both")
    parser.add_argument("--fail-on-blocker", action="store_true", default=False)
    parser.add_argument("--offline-fixtures", default=None)
    parser.add_argument("--changed-paths-file", default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = run_agent_command_center(
        runtime_dir=Path(args.runtime_dir),
        logs_dir=Path(args.logs_dir),
        session_dir=Path(args.session_dir) if args.session_dir else None,
        out_dir=Path(args.out_dir),
        tail_lines=args.tail_lines,
        agents=tuple(args.agents),
        fmt=args.format,
        fail_on_blocker=args.fail_on_blocker,
        offline_fixtures=Path(args.offline_fixtures) if args.offline_fixtures else None,
        changed_paths_file=Path(args.changed_paths_file) if args.changed_paths_file else None,
    )
    print(report.root_cause_summary)
    print(f"first_blocker_layer={report.first_blocker_layer or 'UNKNOWN'}")
    print(f"next_pr_recommendation={report.next_pr_recommendation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
