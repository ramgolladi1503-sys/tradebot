#!/usr/bin/env python3
"""Submit a local agent work request safely.

This CLI is intentionally local-only. It accepts a JSON payload, runs the agent
work contract, scope guard, patch-only approval layer, and optional evidence
writer, then prints a JSON result.

It does not expose an API, webhook, dashboard, broker action, paper order, or
live configuration path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.agent_approval import approve_agent_scope
from core.agent_evidence import write_agent_evidence
from core.agent_scope_guard import assess_agent_scope
from core.agent_work_contract import (
    normalize_agent_work_request,
    validate_agent_work_contract,
)


CLI_OK = 0
CLI_CONTRACT_OR_SCOPE_BLOCKED = 2
CLI_APPROVAL_REJECTED = 3
CLI_PAYLOAD_ERROR = 4


def _load_payload(path: str | Path) -> dict[str, Any]:
    payload_path = Path(path).expanduser()
    try:
        raw = payload_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"failed_to_read_payload:{type(exc).__name__}:{exc}") from exc
    if not isinstance(data, Mapping):
        raise ValueError("payload_must_be_json_object")
    return dict(data)


def submit_agent_work_payload(
    payload: Mapping[str, Any],
    *,
    human_approved: bool = False,
    approved_by: str | None = None,
    write_evidence: bool = True,
    evidence_root: str | Path | None = None,
) -> tuple[int, dict[str, Any]]:
    request = normalize_agent_work_request(payload)
    contract_decision = validate_agent_work_contract(request)
    scope_decision = assess_agent_scope(request, contract_decision=contract_decision)
    approval_decision = approve_agent_scope(
        scope_decision,
        human_approved=human_approved,
        approved_by=approved_by,
    )

    evidence_result = None
    if write_evidence:
        evidence_result = write_agent_evidence(
            request=request,
            scope_decision=scope_decision,
            approval_decision=approval_decision,
            root_dir=evidence_root,
        )

    result = {
        "request": request.to_dict(),
        "contract_decision": contract_decision.to_dict(),
        "scope_decision": scope_decision.to_dict(),
        "approval_decision": approval_decision.to_dict(),
        "evidence_result": evidence_result.to_dict()
        if evidence_result is not None
        else None,
        "safety": {
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "live_mode_touched": False,
            "allowed_for_live_execution": False,
        },
        "metadata": {
            "contract": "agent_work_cli_v1",
            "scope": "local_json_submission_only_no_api_no_webhook_no_runtime",
        },
    }

    if not contract_decision.accepted or not scope_decision.accepted:
        return CLI_CONTRACT_OR_SCOPE_BLOCKED, result
    if not approval_decision.approved:
        return CLI_APPROVAL_REJECTED, result
    return CLI_OK, result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit a local Tradebot agent work JSON payload safely."
    )
    parser.add_argument(
        "--payload", required=True, help="Path to the agent work JSON payload."
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Mark the request as human-approved for patch work.",
    )
    parser.add_argument(
        "--approved-by",
        default=None,
        help="Approver id required when --approve is used.",
    )
    parser.add_argument(
        "--evidence-root",
        default=None,
        help="Optional evidence output directory for tests or local review.",
    )
    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="Skip evidence writing and only print the decision JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        payload = _load_payload(args.payload)
        exit_code, result = submit_agent_work_payload(
            payload,
            human_approved=bool(args.approve),
            approved_by=args.approved_by,
            write_evidence=not bool(args.no_evidence),
            evidence_root=args.evidence_root,
        )
    except ValueError as exc:
        exit_code = CLI_PAYLOAD_ERROR
        result = {
            "error": str(exc),
            "safety": {
                "read_only": True,
                "is_order_action": False,
                "broker_api_called": False,
                "live_mode_touched": False,
                "allowed_for_live_execution": False,
            },
            "metadata": {
                "contract": "agent_work_cli_v1",
                "scope": "payload_error_no_runtime_effects",
            },
        }

    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
