#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.option_e2e_recertification_v4.all_strategy_option_campaign_v1 import (
    build_campaign_universe,
    build_master_analytics,
    write_campaign_universe,
    write_master_analytics,
)


def _load_result_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
    elif isinstance(payload, dict):
        rows = [payload]
    else:
        raise ValueError(f"unsupported_result_payload:{path}")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"result_rows_must_be_objects:{path}")
    return [dict(row) for row in rows]


def _load_completed_results(paths: list[Path]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda item: item.as_posix()):
        results.extend(_load_result_file(path.resolve(strict=True)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build one exhaustive all-strategy CE/PE analytics table, including "
            "runnable, blocked, deferred, filter, and hypothesis rows."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--result-json",
        action="append",
        type=Path,
        default=[],
        help=(
            "Optional completed campaign result JSON. Repeat for multiple files. "
            "Each row must contain entity_id and the published analytics fields."
        ),
    )
    parser.add_argument(
        "--require-complete-universe",
        action="store_true",
        default=False,
        help="Fail when the exhaustive universe still has hard classification gaps.",
    )
    args = parser.parse_args()

    root = args.repo_root.resolve(strict=True)
    output = args.output_dir.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output_directory_not_empty:{output}")
    output.mkdir(parents=True, exist_ok=True)

    universe = build_campaign_universe(root)
    universe_dir = output / "universe"
    analytics_dir = output / "analytics"
    universe_hashes = write_campaign_universe(universe, universe_dir)
    completed_results = _load_completed_results(args.result_json)
    rows, summary = build_master_analytics(universe, completed_results)
    analytics_hashes = write_master_analytics(rows, summary, analytics_dir)

    manifest = {
        "schema_version": "all_strategy_option_analytics_run_manifest_v1",
        "universe_semantic_hash": universe.summary["semantic_hash"],
        "universe_coverage_complete": universe.summary["coverage_complete"],
        "universe_hard_gap_count": universe.summary["hard_gap_count"],
        "analytics_semantic_hash": summary["semantic_hash"],
        "analytics_entity_count": summary["analytics_entity_count"],
        "completed_result_count": summary["completed_result_count"],
        "ranking_eligible_count": summary["ranking_eligible_count"],
        "universe_artifact_hashes": universe_hashes,
        "analytics_artifact_hashes": analytics_hashes,
        "result_input_count": len(args.result_json),
        "research_only": True,
        "read_only": True,
        "broker_api_called": False,
        "is_order_action": False,
        "allowed_for_live_execution": False,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(manifest, sort_keys=True, indent=2))
    if args.require_complete_universe and not universe.summary["coverage_complete"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
