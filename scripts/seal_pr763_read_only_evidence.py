#!/usr/bin/env python3
"""Create the canonical PR #782 seal markers for one closed evidence root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ai_reliability_agent.pr763_session import verify_sealed_evidence_root
from core.unified_live_validation_pr748_756.seal import seal_evidence_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", required=True, type=Path)
    args = parser.parse_args()

    root = args.evidence_root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit("EVIDENCE_ROOT_MISSING")
    if any((root / name).exists() for name in ("artifact_manifest.json", "SHA256SUMS", "SEALED")):
        raise SystemExit("EVIDENCE_ROOT_ALREADY_SEALED_OR_PARTIALLY_SEALED")

    manifest = seal_evidence_root(root)
    gate = verify_sealed_evidence_root(root)
    report = {
        "verdict": "PASS_CANONICAL_PR782_SEAL" if gate.passed else "FAILED_CANONICAL_PR782_SEAL",
        "evidence_root": str(root),
        "artifact_count": manifest.get("artifact_count"),
        "artifact_manifest_sha256": manifest.get("artifact_manifest_sha256"),
        "gate": {
            "gate_id": gate.gate_id,
            "passed": gate.passed,
            "evidence": gate.evidence,
        },
        "read_only": True,
        "is_order_action": False,
        "broker_write_authority": False,
        "order_authority": False,
        "allowed_for_live_execution": False,
        "allowed_for_paper_execution": False,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
