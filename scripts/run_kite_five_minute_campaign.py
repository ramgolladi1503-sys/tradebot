#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.kite_five_minute_campaign import (
    build_exposure_ledger,
    certify_archive,
    run_campaign,
)
from research.kite_five_minute_campaign.common import file_sha256


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the governed Kite five-minute development campaign.")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--output-root", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.output_root).resolve()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    summary = certify_archive(args.archive, root, commit=commit)
    input_dir = root / "research/kite_five_minute_campaign/input"
    manifest_path = input_dir / "accepted_underlying_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    extract_root = input_dir / "extracted"
    for row in manifest:
        row["absolute_path"] = str(extract_root / row["relative_path"])
    exposure = build_exposure_ledger(
        root,
        manifest,
        root / "research/data_governance",
        commit=commit,
    )
    source_manifest_hash = file_sha256(manifest_path)
    first = run_campaign(
        manifest,
        root / "research/kite_five_minute_campaign/evidence/run_a",
        source_manifest_hash=source_manifest_hash,
        code_commit=commit,
    )
    second = run_campaign(
        manifest,
        root / "research/kite_five_minute_campaign/evidence/run_b",
        source_manifest_hash=source_manifest_hash,
        code_commit=commit,
    )
    deterministic = first == second
    print(json.dumps({
        "archive": summary,
        "exposure": exposure,
        "deterministic": deterministic,
        "verdict": first["verdict"],
        "candidate_bundle_hash": first["candidate_bundle_hash"],
    }, indent=2, sort_keys=True))
    return 0 if deterministic else 2


if __name__ == "__main__":
    raise SystemExit(main())
