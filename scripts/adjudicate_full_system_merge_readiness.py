#!/usr/bin/env python3
"""Adjudicate a sealed full-system observation root from primitive evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


COMPONENTS = (
    "strategy_engines", "candidate_funnel", "ranking", "market_regime",
    "option_chain", "ai_reliability", "live_analytics", "ui_runtime_snapshot",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def adjudicate(root: Path, expected_sha: str | None = None) -> dict:
    root = root.resolve()
    seal = (root / "SEALED").is_file()
    sums = root / "SHA256SUMS"
    integrity = False
    if seal and sums.is_file():
        integrity = subprocess.run(
            ["shasum", "-c", str(sums)], cwd=root, capture_output=True, text=True,
        ).returncode == 0
    identity = _json(root / "process_identity.json") if (root / "process_identity.json").is_file() else {}
    manifest = _json(root / "presession_manifest.json") if (root / "presession_manifest.json").is_file() else {}
    expected_sha = str(expected_sha or manifest.get("commit_sha") or identity.get("producer_sha") or "")
    wiring = _json(root / "meg_wiring_evidence.json") if (root / "meg_wiring_evidence.json").is_file() else {}
    drain = _json(root / "shutdown_drain.json") if (root / "shutdown_drain.json").is_file() else {}
    subscription = wiring.get("subscription_evidence") or {}
    lifecycle = subscription.get("token_lifecycle") or {}
    nifty_rows = [row for row in lifecycle.values() if str(row.get("symbol", "")).upper() == "NIFTY"]
    nifty_count = sum(int(row.get("post_mode_full_count") or 0) for row in nifty_rows)
    nifty_post_mode = any(
        (row.get("latest_post_mode_full_epoch") or row.get("latest_post_mode_full_receipt_epoch") or row.get("first_post_mode_full_epoch")) is not None
        and float(row.get("latest_post_mode_full_epoch") or row.get("latest_post_mode_full_receipt_epoch") or row.get("first_post_mode_full_epoch")) > float(row.get("mode_request_succeeded_epoch"))
        for row in nifty_rows
        if row.get("mode_request_succeeded_epoch") is not None
    )
    rejection_path = root / "depth_rejections.jsonl"
    rejection_count = 0
    rejection_reasons: dict[str, int] = {}
    if rejection_path.is_file():
        for line in rejection_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            rejection_count += 1
            reason = str(row.get("reason_code") or "UNKNOWN_REJECTION")
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
    depth_state = drain.get("depth_state") or {}
    component_status = {name: "UNKNOWN" for name in COMPONENTS}
    # This launcher is a read-only MEG composition root. Its source imports
    # candidate extraction/authority serialization only; it does not invoke
    # strategy, ranking, regime, option-chain, AI, analytics, or UI engines.
    for name in COMPONENTS:
        component_status[name] = "NOT_ENABLED_IN_THIS_RUNTIME"
    mandatory = []
    unknown = [name for name, status in component_status.items() if status == "UNKNOWN"]
    blockers = []
    if not seal or not integrity:
        blockers.append("SEALED_ROOT_INVALID")
    if not expected_sha or identity.get("producer_sha") != expected_sha or manifest.get("commit_sha") != expected_sha:
        blockers.append("PRODUCER_SHA_MISMATCH")
    if not (nifty_post_mode and nifty_count > 0):
        blockers.append("INDEX_FULL_PACKET_NOT_OBSERVED")
    if int(depth_state.get("rejected") or 0) != rejection_count:
        blockers.append("DEPTH_REJECTION_PROVENANCE_MISMATCH")
    if unknown:
        blockers.append("UNKNOWN_MANDATORY_COMPONENT")
    return {
        "verdict": "TRADEBOT_FULL_SYSTEM_MERGE_READY" if not blockers else "TRADEBOT_FULL_SYSTEM_MERGE_BLOCKED",
        "sealed_root_valid": bool(seal and integrity),
        "producer_sha": identity.get("producer_sha"),
        "session_id": manifest.get("capture_session_id"),
        "nifty_full_packet": {"post_mode_full": nifty_post_mode, "count": nifty_count},
        "depth_rejection_provenance": {"count": rejection_count, "by_reason": rejection_reasons, "canonical_rejected": int(depth_state.get("rejected") or 0)},
        "components": component_status,
        "mandatory_components": mandatory,
        "unknown_components": unknown,
        "blockers": blockers,
        "broker_write_authority": False,
        "order_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--expected-sha")
    args = parser.parse_args()
    print(json.dumps(adjudicate(args.evidence_root, args.expected_sha), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
