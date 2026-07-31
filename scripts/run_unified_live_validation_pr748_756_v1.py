#!/usr/bin/env python3
"""Prepare a read-only unified evidence campaign run directory.

This wrapper intentionally does not launch `run_live.sh` by itself. It creates
the immutable run identity, static manifest, and launch command so a human can
start exactly one guarded runtime process during market hours.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.unified_live_validation_pr748_756.campaign_contract import (
    ENABLE_ENV,
    build_campaign_identity,
    build_composition_manifest,
    current_commit_sha,
    require_campaign_enabled,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", default="runtime/diagnostics/unified_live_validation_pr748_756_v1")
    parser.add_argument("--origin-main-sha", required=True)
    parser.add_argument("--nonce")
    args = parser.parse_args()

    require_campaign_enabled()
    root = Path(args.evidence_root)
    commit = current_commit_sha(".")
    manifest = build_composition_manifest(origin_main_sha=args.origin_main_sha, integrated_commit_sha=commit)
    presession = root / "presession"
    presession.mkdir(parents=True, exist_ok=True)
    (presession / "composition_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    identity = build_campaign_identity(
        evidence_root=root,
        campaign_commit_sha=commit,
        composition_manifest_sha=manifest["composition_manifest_sha256"],
        nonce=args.nonce,
    )
    run_root = Path(identity.evidence_root)
    for child in ("presession", "live", "postmarket", "per_pr"):
        (run_root / child).mkdir(parents=True, exist_ok=True)
    (run_root / "presession" / "campaign_identity.json").write_text(
        json.dumps(identity.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    launch = {
        "state": "READY_FOR_LIVE_START",
        "run_id": identity.run_id,
        "evidence_root": str(run_root),
        "launch_command": (
            f"{ENABLE_ENV}=true TRADEBOT_READ_ONLY=true "
            f"UNIFIED_LIVE_VALIDATION_PR748_756_RUN_ID={identity.run_id} ./run_live.sh"
        ),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    (run_root / "presession" / "launch_preflight.json").write_text(
        json.dumps(launch, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(launch, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

