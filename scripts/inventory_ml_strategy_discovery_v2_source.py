#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from research.ml_strategy_discovery_v2.artifacts import sha256_file
from research.ml_strategy_discovery_v2.source import load_and_verify_manifest


def inventory(corpus_dir: str | Path, manifest_path: str | Path) -> dict:
    corpus = Path(corpus_dir).expanduser().resolve()
    payload, identity = load_and_verify_manifest(manifest_path)
    manifest_by_path = {record["logical_path"]: record for record in payload["records"]}
    local: dict[str, Path] = {}
    duplicates: list[str] = []
    outside_layout: list[str] = []
    for path in sorted(corpus.rglob("*.parquet")):
        try:
            relative = path.resolve().relative_to(corpus)
        except ValueError:
            outside_layout.append(str(path))
            continue
        if len(relative.parts) != 3 or relative.parts[1] != "underlying":
            outside_layout.append(str(relative))
            continue
        logical = str(Path("runtime/upstox_candidate_replay") / relative)
        if logical in local:
            duplicates.append(logical)
        local[logical] = path
    local_paths = set(local)
    manifest_paths = set(manifest_by_path)
    added = sorted(local_paths - manifest_paths)
    missing = sorted(manifest_paths - local_paths)
    changed: list[dict] = []
    for logical in sorted(local_paths & manifest_paths):
        actual = sha256_file(local[logical])
        expected = str(manifest_by_path[logical]["actual_sha256"])
        if actual != expected:
            changed.append(
                {
                    "logical_path": logical,
                    "expected_sha256": expected,
                    "actual_sha256": actual,
                }
            )
    by_instrument: Counter[str] = Counter()
    by_date: defaultdict[str, list[str]] = defaultdict(list)
    for logical in added:
        stem = Path(logical).stem
        symbol, compact = stem.rsplit("_", 1) if "_" in stem else (stem, "")
        by_instrument[symbol] += 1
        if len(compact) == 8 and compact.isdigit():
            by_date[f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"].append(logical)
        else:
            outside_layout.append(logical)
    verdict = (
        "SOURCE_DELTA_INVALID"
        if missing or changed or duplicates or outside_layout
        else "SOURCE_DELTA_VALID"
    )
    return {
        "manifest_identity": identity,
        "total_local_parquet": len(local),
        "total_manifest_records": len(manifest_paths),
        "added_count": len(added),
        "missing_count": len(missing),
        "changed_byte_count": len(changed),
        "duplicate_count": len(duplicates),
        "outside_layout_count": len(outside_layout),
        "added_paths": added,
        "missing_paths": missing,
        "changed_records": changed,
        "duplicates": sorted(duplicates),
        "outside_expected_layout": sorted(set(outside_layout)),
        "delta_by_instrument": dict(sorted(by_instrument.items())),
        "delta_by_session_date": dict(sorted(by_date.items())),
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory source delta against a certified manifest"
    )
    parser.add_argument("--corpus-dir", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    result = inventory(args.corpus_dir, args.manifest_path)
    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "inventory.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output / "report.md").write_text(
        "# V2 Source Inventory\n\n"
        f"- Verdict: `{result['verdict']}`\n"
        f"- Local parquet: `{result['total_local_parquet']}`\n"
        f"- Manifest records: `{result['total_manifest_records']}`\n"
        f"- Added: `{result['added_count']}`\n"
        f"- Missing: `{result['missing_count']}`\n"
        f"- Changed bytes: `{result['changed_byte_count']}`\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
