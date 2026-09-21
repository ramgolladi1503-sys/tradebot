#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from research.reversal_probability_profile_v1.campaign import CampaignConfig, run_campaign

ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "research/reversal_probability_profile_v1/verified_data_binding.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def candidate_paths(entry: dict, explicit: Path | None) -> list[Path]:
    paths: list[Path] = []
    if explicit is not None:
        paths.append(explicit)
    preferred = entry.get("preferred_path")
    if preferred:
        paths.append(Path(preferred))
    relative = entry.get("repo_relative_path")
    if relative:
        paths.append(ROOT / relative)
    # TradeBot data is often externalized to this volume; preserve the suffix.
    if relative:
        paths.append(Path("/Volumes/TradeBotData") / relative)
        paths.append(Path("/Volumes/TradeBotData/tradebot-os") / relative)
    deduped: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p.expanduser())
        if key not in seen:
            seen.add(key)
            deduped.append(p.expanduser())
    return deduped


def resolve_authoritative_input(explicit: Path | None = None) -> tuple[Path, dict]:
    binding = json.loads(BINDING.read_text(encoding="utf-8"))
    attempts: list[dict] = []
    for entry in binding["accepted_inputs"]:
        expected = str(entry["sha256"]).lower()
        for path in candidate_paths(entry, explicit):
            if not path.is_file():
                attempts.append({"path": str(path), "status": "MISSING", "authority_id": entry["authority_id"]})
                continue
            actual = sha256_file(path)
            if actual == expected:
                return path, entry
            attempts.append({
                "path": str(path),
                "status": "SHA_MISMATCH",
                "authority_id": entry["authority_id"],
                "expected_sha256": expected,
                "actual_sha256": actual,
            })
        # An explicit path only needs to be hashed against all accepted authorities.
    raise SystemExit(
        "RPP_INPUT_AUTHORITY_FAIL\n" + json.dumps({"binding": str(BINDING), "attempts": attempts}, indent=2)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run RPP V1 only after exact-SHA verification of an accepted NIFTY 1-minute authority."
    )
    parser.add_argument("--input", help="Optional explicit candidate path. Exact accepted SHA is still required.")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "research/evidence/reversal_probability_profile_v1"),
    )
    parser.add_argument("--cost-bps", type=float, default=5.0)
    args = parser.parse_args()

    path, authority = resolve_authoritative_input(Path(args.input) if args.input else None)
    print("RPP_INPUT_AUTHORITY=PASS")
    print(f"RPP_INPUT_AUTHORITY_ID={authority['authority_id']}")
    print(f"RPP_INPUT_PATH={path}")
    print(f"RPP_INPUT_SHA256={authority['sha256']}")
    print("RPP_HOLDOUT_ACCESS=false")
    print("RPP_BROKER_WRITE_AUTHORITY=false")

    report = run_campaign(
        path,
        args.output_dir,
        CampaignConfig(round_trip_cost_bps=float(args.cost_bps)),
    )
    report_path = Path(args.output_dir) / "report.json"
    print(f"RPP_REPORT={report_path}")
    print(f"RPP_VERDICT={report.get('verdict')}")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
