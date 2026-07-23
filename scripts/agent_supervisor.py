#!/usr/bin/env python3
"""CLI for the local Tradebot agent worktree supervisor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from core.agent_supervisor import (
    claim_contract,
    get_contract_status,
    load_contract_file,
    normalize_supervisor_contract,
    preflight_contract,
    record_independent_review,
    release_contract,
    verify_contract,
)


CLI_OK = 0
CLI_BLOCKED = 2
CLI_INPUT_ERROR = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Supervise an isolated Tradebot agent worktree without broker or live access."
    )
    parser.add_argument(
        "command",
        choices=("preflight", "claim", "verify", "review", "release", "status"),
    )
    parser.add_argument("--contract", required=True, help="Path to a supervisor task JSON file.")
    parser.add_argument("--approve", action="store_true", help="Human-approve patch scope.")
    parser.add_argument("--approved-by", default=None, help="Approver id used with --approve.")
    parser.add_argument("--review", default=None, help="Independent review JSON for the review command.")
    parser.add_argument("--force", action="store_true", help="Force release an unfinished claim.")
    return parser


def _load_json_object(path: str | Path) -> dict:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("review_must_be_json_object")
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = load_contract_file(args.contract)
        contract = normalize_supervisor_contract(payload)
        if args.command == "preflight":
            result = preflight_contract(
                contract,
                human_approved=bool(args.approve),
                approved_by=args.approved_by,
            )
        elif args.command == "claim":
            result = claim_contract(
                contract,
                human_approved=bool(args.approve),
                approved_by=args.approved_by,
            )
        elif args.command == "verify":
            result = verify_contract(contract)
        elif args.command == "review":
            if not args.review:
                raise ValueError("--review is required for the review command")
            result = record_independent_review(contract, _load_json_object(args.review))
        elif args.command == "release":
            result = release_contract(contract, force=bool(args.force))
        else:
            result = get_contract_status(contract)
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
        return CLI_OK if result.accepted else CLI_BLOCKED
    except Exception as exc:
        error = {
            "error": f"{type(exc).__name__}:{exc}",
            "safety": {
                "read_only_from_trading_runtime": True,
                "is_order_action": False,
                "broker_api_called": False,
                "live_mode_touched": False,
                "allowed_for_live_execution": False,
            },
        }
        print(json.dumps(error, indent=2, sort_keys=True))
        return CLI_INPUT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
