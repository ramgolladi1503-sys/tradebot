#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.opening_range_retest.replay_engine import (
    LEDGER_ARTIFACT_FILENAME,
    merge_replay_artifacts,
    run_replay,
    write_replay_artifacts,
)


def _default_ledger_path(*, output_dir: Path, shard_count: int | None, shard_index: int | None) -> Path:
    docs_dir = PROJECT_ROOT / "docs" / "agent_reviews"
    if output_dir.resolve() != docs_dir.resolve():
        return output_dir / LEDGER_ARTIFACT_FILENAME
    if shard_count is not None and shard_index is not None:
        return (
            PROJECT_ROOT
            / ".runtime"
            / "opening_range_retest_causal_replay"
            / "shards"
            / f"opening_range_retest_causal_replay_ledger_v1.shard-{shard_index:02d}-of-{shard_count:02d}.json"
        )
    return PROJECT_ROOT / ".runtime" / "opening_range_retest_causal_replay" / "opening_range_retest_causal_replay_ledger_v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 1 opening-range-retest causal replay artifacts.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/agent_reviews/four_strategy_dataset_manifest_v3.json"),
        help="Manifest path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/agent_reviews"),
        help="Tracked bounded artifact directory.",
    )
    parser.add_argument(
        "--ledger-path",
        type=Path,
        default=None,
        help="Untracked full emission ledger path. Defaults to the output directory for non-docs runs and a .runtime path for docs runs.",
    )
    parser.add_argument(
        "--limit-sessions",
        type=int,
        default=None,
        help="Optional limit for deterministic smoke runs.",
    )
    parser.add_argument(
        "--allow-manifest-without-inventory",
        action="store_true",
        help="Diagnostic only. Allow fallback root scanning when authoritative inventory cannot be resolved. This mode can never produce OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=max(1, min(8, (os.cpu_count() or 1))),
        help="Parallel session workers for authoritative replay.",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=None,
        help="Deterministic shard count for authoritative replay.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=None,
        help="Zero-based deterministic shard index for authoritative replay.",
    )
    parser.add_argument(
        "--merge-shard-dir",
        action="append",
        dest="merge_shard_dirs",
        type=Path,
        default=None,
        help="Merge previously generated shard artifact directories instead of running replay.",
    )
    args = parser.parse_args()

    if (args.shard_count is None) != (args.shard_index is None):
        parser.error("--shard-count and --shard-index must be provided together")
    ledger_path = args.ledger_path or _default_ledger_path(
        output_dir=args.output_dir,
        shard_count=args.shard_count,
        shard_index=args.shard_index,
    )
    if args.merge_shard_dirs:
        if args.allow_manifest_without_inventory:
            parser.error("--allow-manifest-without-inventory cannot be used with --merge-shard-dir")
        run = merge_replay_artifacts(shard_artifact_dirs=args.merge_shard_dirs)
    else:
        run = run_replay(
            manifest_path=args.manifest,
            require_inventory=not args.allow_manifest_without_inventory,
            limit_sessions=args.limit_sessions,
            max_workers=args.max_workers,
            shard_count=args.shard_count,
            shard_index=args.shard_index,
        )
    paths = write_replay_artifacts(run, output_dir=args.output_dir, ledger_path=ledger_path)
    print(run.summary["phase1_verdict"])
    print(f"contract={paths['contract']}")
    print(f"source_manifest={paths['source_manifest']}")
    print(f"summary={paths['summary']}")
    shard_metadata = dict(run.summary.get("shard_metadata") or {})
    print(f"shard_count={shard_metadata.get('shard_count')}")
    print(f"shard_index={shard_metadata.get('shard_index')}")
    print(f"merged_from_shards={shard_metadata.get('merged_from_shards')}")
    if paths["ledger"] is not None and Path(paths["ledger"]).exists():
        ledger = Path(paths["ledger"])
        print(f"ledger={ledger}")
        print(f"ledger_bytes={ledger.stat().st_size}")
    print(f"diagnostic_mode={run.summary['diagnostic_mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
