"""Local paper trading runbook command.

Usage:
    PYTHONPATH=. python scripts/paper_trading_runbook.py --session-snapshot path/to/session.json

This command validates an already-produced paper session snapshot through the
paper session gate and prints a JSON runbook report. It does not start runtime,
call brokers, mutate paper orders/ledgers, or write files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
from typing import Any

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from core.paper_trading_runbook_command import (
    RUNBOOK_READY,
    build_paper_trading_runbook_report,
)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("session snapshot must be a JSON object")
    return payload


def run_command(session_snapshot_path: Path) -> dict[str, Any]:
    snapshot = _load_json_object(session_snapshot_path)
    report = build_paper_trading_runbook_report(snapshot)
    return report.to_dict()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a completed PAPER session snapshot with the runbook gate."
    )
    parser.add_argument(
        "--session-snapshot",
        required=True,
        help="Path to completed paper session snapshot JSON",
    )
    args = parser.parse_args()

    payload = run_command(Path(args.session_snapshot))
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if payload.get("state") == RUNBOOK_READY else 2


if __name__ == "__main__":
    raise SystemExit(main())
