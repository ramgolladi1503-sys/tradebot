from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from core.analytics.proposal_verify import (
    load_json,
    load_snapshot,
    verify_proposal,
    write_verification,
)


def _failed_report(
    *, proposal_path: Path, snapshot_path: Path, reason: str
) -> dict[str, Any]:
    return {
        "proposal_path": str(proposal_path),
        "snapshot_path": str(snapshot_path),
        "status": "FAIL",
        "summary": {
            "total_proposals": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
        },
        "results": [],
        "error": reason,
    }


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify offline config_delta proposal against user-supplied snapshot."
    )
    parser.add_argument(
        "--proposal", required=True, help="Path to config_delta_proposal.json"
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Path to user-supplied config snapshot (json|yaml)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_cli().parse_args(argv)
    proposal_path = Path(args.proposal)
    snapshot_path = Path(args.snapshot)
    out_dir = proposal_path.parent

    try:
        proposal = load_json(proposal_path)
    except Exception as exc:
        report = _failed_report(
            proposal_path=proposal_path,
            snapshot_path=snapshot_path,
            reason=f"proposal_load_failed:{type(exc).__name__}:{exc}",
        )
        md_path, json_path = write_verification(report, out_dir)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "verification_markdown_path": str(md_path),
                    "verification_json_path": str(json_path),
                    "error": report.get("error"),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 2

    try:
        snapshot = load_snapshot(snapshot_path)
    except Exception as exc:
        report = _failed_report(
            proposal_path=proposal_path,
            snapshot_path=snapshot_path,
            reason=f"snapshot_load_failed:{type(exc).__name__}:{exc}",
        )
        md_path, json_path = write_verification(report, out_dir)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "verification_markdown_path": str(md_path),
                    "verification_json_path": str(json_path),
                    "error": report.get("error"),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
        )
        return 2

    report = verify_proposal(proposal, snapshot)
    report["proposal_path"] = str(proposal_path)
    report["snapshot_path"] = str(snapshot_path)

    md_path, json_path = write_verification(report, out_dir)
    print(
        json.dumps(
            {
                "status": report["status"],
                "verification_markdown_path": str(md_path),
                "verification_json_path": str(json_path),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )

    if report["status"] == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
