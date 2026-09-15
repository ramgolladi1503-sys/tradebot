#!/usr/bin/env python3
"""Read-only MROS morning-controller entrypoint; never invokes broker/order code."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.morning_controller import MorningController


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--state-root", type=Path, default=Path("/Volumes/TradeBotData/runtime/mros_morning_controller"))
    parser.add_argument("--source-sha")
    parser.add_argument("--config-sha")
    parser.add_argument("--instrument-sha")
    parser.add_argument("--stage-evidence", type=Path)
    parser.add_argument("--governor", action="store_true", help="derive stages from existing read-only MROS governor")
    parser.add_argument("--external-root", type=Path, default=Path("/Volumes/TradeBotData"))
    parser.add_argument("--release-store-root", type=Path)
    parser.add_argument("--kite-instruments-file", type=Path)
    args = parser.parse_args()
    if args.source_sha is None:
        try:
            args.source_sha = subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True, timeout=15).strip()
        except (OSError, subprocess.SubprocessError):
            args.source_sha = "UNKNOWN_SOURCE"
    if args.config_sha is None:
        h = hashlib.sha256(); config_files = 0
        for path_text in sorted(repo_root.glob("config/**/*")):
            if path_text.is_file(): config_files += 1; h.update(str(path_text.relative_to(repo_root)).encode()); h.update(path_text.read_bytes())
        args.config_sha = h.hexdigest() if config_files else "UNKNOWN_CONFIG"
    if args.instrument_sha is None:
        args.instrument_sha = "UNKNOWN_NO_CURRENT_INSTRUMENT_AUTHORITY"
    evidence = json.loads(args.stage_evidence.read_text(encoding="utf-8")) if args.stage_evidence else {}
    if args.governor:
        from core.mros_daily_governor import MROSDailyGovernor
        plan = MROSDailyGovernor(repo_root=repo_root, session_date=args.session_date,
            external_root=args.external_root, release_store_root=args.release_store_root,
            instrument_master_file=args.kite_instruments_file).evaluate_morning_readiness()
        governed = MorningController.evidence_from_governor(plan)
        governed.update(evidence)
        evidence = governed
    result = MorningController(args.state_root).run(session_date=args.session_date, source_sha=args.source_sha,
        config_sha=args.config_sha, instrument_sha=args.instrument_sha, evidence=evidence)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["session_classification"] == "FULL" else 2


if __name__ == "__main__": raise SystemExit(main())
