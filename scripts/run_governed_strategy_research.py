#!/usr/bin/env python3
"""CLI for the fail-closed agentic strategy-research control plane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from core.governed_strategy_research import (
    AgentRole,
    GovernedResearchStore,
    ResearchError,
)


def _load(path: str) -> dict:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ResearchError("input_json_must_be_object")
    return payload


def _print(payload: object) -> None:
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Governed Codex + Antigravity strategy research")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create one research run")
    init.add_argument("--run-dir", required=True)
    init.add_argument("--strategy-id", required=True)
    init.add_argument("--title", required=True)
    init.add_argument("--objective", required=True)
    init.add_argument("--implementer", default="codex")
    init.add_argument("--reviewer", default="antigravity")

    freeze = sub.add_parser("freeze", help="Freeze a hypothesis before outcomes")
    freeze.add_argument("--run-dir", required=True)
    freeze.add_argument("--hypothesis", required=True)

    packet = sub.add_parser("packet", help="Generate an agent work packet")
    packet.add_argument("--run-dir", required=True)
    packet.add_argument("--agent", required=True)
    packet.add_argument("--role", required=True, choices=[role.value.lower() for role in AgentRole])

    implementation = sub.add_parser("record-implementation")
    implementation.add_argument("--run-dir", required=True)
    implementation.add_argument("--evidence", required=True)

    review = sub.add_parser("record-review")
    review.add_argument("--run-dir", required=True)
    review.add_argument("--evidence", required=True)

    validation = sub.add_parser("record-validation")
    validation.add_argument("--run-dir", required=True)
    validation.add_argument("--evidence", required=True)

    approve = sub.add_parser("approve-paper")
    approve.add_argument("--run-dir", required=True)
    approve.add_argument("--approved-by", required=True)

    status = sub.add_parser("status")
    status.add_argument("--run-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            store = GovernedResearchStore.initialize(
                args.run_dir,
                strategy_id=args.strategy_id,
                title=args.title,
                objective=args.objective,
                implementer=args.implementer,
                reviewer=args.reviewer,
            )
            _print(store.status())
            return 0

        store = GovernedResearchStore(args.run_dir)
        if args.command == "freeze":
            _print(store.freeze_hypothesis(_load(args.hypothesis)))
        elif args.command == "packet":
            path = store.build_agent_packet(agent=args.agent, role=args.role.upper())
            _print({"packet_path": str(path), "status": store.status().to_dict()})
        elif args.command == "record-implementation":
            _print(store.record_implementation(_load(args.evidence)))
        elif args.command == "record-review":
            _print(store.record_review(_load(args.evidence)))
        elif args.command == "record-validation":
            _print(store.record_validation(_load(args.evidence)))
        elif args.command == "approve-paper":
            _print(store.approve_paper(approved_by=args.approved_by))
        elif args.command == "status":
            _print(store.status())
        return 0
    except (ResearchError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"accepted": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
