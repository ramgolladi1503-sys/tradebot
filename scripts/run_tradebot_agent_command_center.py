#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.agents.command_center import run_agent_command_center


def _truthy(value: str | bool | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _default_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"agent_command_center_{stamp}_{uuid.uuid4().hex[:8]}"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Tradebot Agent Command Center."
    )
    parser.add_argument("--runtime-dir", default=".runtime")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--session-dir", default=None)
    parser.add_argument("--out-dir", default=str(Path(".runtime") / "agent_reports"))
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--watch", action="store_true", default=False)
    parser.add_argument("--once", action="store_true", default=False)
    parser.add_argument("--interval-sec", type=float, default=10.0)
    parser.add_argument("--copy-latest", default="true")
    parser.add_argument("--tail-lines", type=int, default=5000)
    parser.add_argument("--agents", nargs="*", default=["all"])
    parser.add_argument(
        "--format", choices=("json", "markdown", "both"), default="both"
    )
    parser.add_argument("--fail-on-blocker", action="store_true", default=False)
    parser.add_argument("--offline-fixtures", default=None)
    parser.add_argument("--changed-paths-file", default=None)
    return parser.parse_args(argv)


def _resolve_run_paths(args: argparse.Namespace) -> tuple[Path, Path, str]:
    output_root = Path(args.out_dir).expanduser()
    run_root = Path(args.run_dir).expanduser() if args.run_dir else output_root / "runs"
    run_id = args.run_id or _default_run_id()
    return output_root, run_root, run_id


def _copy_latest_outputs(source_dir: Path, destination_dir: Path) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    if not source_dir.exists():
        return
    for path in sorted(source_dir.glob("*_latest.*")):
        if path.is_file():
            shutil.copy2(path, destination_dir / path.name)


def _run_single_iteration(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path,
    tail_lines: int,
    agents: Sequence[str],
    fmt: str,
    fail_on_blocker: bool,
    offline_fixtures: Path | None,
    changed_paths_file: Path | None,
    copy_latest: bool,
    output_root: Path,
    changed_paths: Iterable[str] | None = None,
) -> int:
    report = run_agent_command_center(
        runtime_dir=runtime_dir,
        logs_dir=logs_dir,
        session_dir=session_dir,
        out_dir=session_dir,
        tail_lines=tail_lines,
        agents=agents,
        fmt=fmt,
        fail_on_blocker=fail_on_blocker,
        offline_fixtures=offline_fixtures,
        changed_paths_file=changed_paths_file,
        changed_paths=changed_paths,
    )
    if copy_latest:
        _copy_latest_outputs(session_dir, output_root)
    print(report.root_cause_summary)
    print(f"first_blocker_layer={report.first_blocker_layer or 'UNKNOWN'}")
    print(f"next_pr_recommendation={report.next_pr_recommendation}")
    return 0


def _run_watch_loop(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path,
    tail_lines: int,
    agents: Sequence[str],
    fmt: str,
    fail_on_blocker: bool,
    offline_fixtures: Path | None,
    changed_paths_file: Path | None,
    copy_latest: bool,
    output_root: Path,
    interval_sec: float,
    once: bool,
) -> int:
    try:
        while True:
            _run_single_iteration(
                runtime_dir=runtime_dir,
                logs_dir=logs_dir,
                session_dir=session_dir,
                tail_lines=tail_lines,
                agents=agents,
                fmt=fmt,
                fail_on_blocker=fail_on_blocker,
                offline_fixtures=offline_fixtures,
                changed_paths_file=changed_paths_file,
                copy_latest=copy_latest,
                output_root=output_root,
            )
            if once:
                return 0
            time.sleep(max(interval_sec, 0.0))
    except KeyboardInterrupt:
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    runtime_dir = Path(args.runtime_dir)
    logs_dir = Path(args.logs_dir)
    session_dir = Path(args.session_dir).expanduser() if args.session_dir else None
    output_root, run_root, run_id = _resolve_run_paths(args)
    resolved_session_dir = session_dir or (run_root / run_id)
    resolved_session_dir.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    offline_fixtures = Path(args.offline_fixtures) if args.offline_fixtures else None
    changed_paths_file = (
        Path(args.changed_paths_file) if args.changed_paths_file else None
    )
    copy_latest = _truthy(args.copy_latest)
    agents = tuple(args.agents)

    if args.watch:
        return _run_watch_loop(
            runtime_dir=runtime_dir,
            logs_dir=logs_dir,
            session_dir=resolved_session_dir,
            tail_lines=args.tail_lines,
            agents=agents,
            fmt=args.format,
            fail_on_blocker=args.fail_on_blocker,
            offline_fixtures=offline_fixtures,
            changed_paths_file=changed_paths_file,
            copy_latest=copy_latest,
            output_root=output_root,
            interval_sec=args.interval_sec,
            once=args.once,
        )

    return _run_single_iteration(
        runtime_dir=runtime_dir,
        logs_dir=logs_dir,
        session_dir=resolved_session_dir,
        tail_lines=args.tail_lines,
        agents=agents,
        fmt=args.format,
        fail_on_blocker=args.fail_on_blocker,
        offline_fixtures=offline_fixtures,
        changed_paths_file=changed_paths_file,
        copy_latest=copy_latest,
        output_root=output_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
