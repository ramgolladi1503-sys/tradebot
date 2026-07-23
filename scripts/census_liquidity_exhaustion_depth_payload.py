#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from core.research_backtest_integrity import (
    RESEARCH_NON_CANDLE_QUOTE,
    load_research_candle_parquet,
)
from research.liquidity_exhaustion_depth_schema_v2.payload_census import census_depth_series

CAMPAIGN_ID = "LIQUIDITY_EXHAUSTION_DEPTH_PAYLOAD_CENSUS_V2"
EXPECTED_ARCHIVE_SHA256 = "8c5fd5cded6475347c94f073b3411d6636c34dcc256243270e23ec8daf6b35f7"
EXPECTED_QUOTE_FILES = 129
EXPECTED_QUOTE_ROWS = 2778666


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def semantic_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def run_census(corpus_root: Path, output: Path) -> dict[str, Any]:
    quote_paths: list[Path] = []
    for path in sorted(corpus_root.glob("*/underlying/*.parquet")):
        classification, _, _ = load_research_candle_parquet(path)
        if classification == RESEARCH_NON_CANDLE_QUOTE:
            quote_paths.append(path)
    if len(quote_paths) != EXPECTED_QUOTE_FILES:
        raise RuntimeError(f"expected {EXPECTED_QUOTE_FILES} quote files, found {len(quote_paths)}")

    file_results: list[dict[str, Any]] = []
    for index, path in enumerate(quote_paths, start=1):
        frame = pd.read_parquet(path, columns=["depth", "symbol", "token"])
        result = census_depth_series(frame["depth"])
        result.update(
            {
                "source": path.relative_to(corpus_root).as_posix(),
                "symbol": str(frame["symbol"].dropna().iloc[0]),
                "token": str(frame["token"].dropna().iloc[0]),
            }
        )
        file_results.append(result)
        if index % 25 == 0:
            print(f"censused {index}/{len(quote_paths)} files", flush=True)

    total_rows = sum(item["row_count"] for item in file_results)
    if total_rows != EXPECTED_QUOTE_ROWS:
        raise RuntimeError(f"expected {EXPECTED_QUOTE_ROWS} quote rows, found {total_rows}")

    totals = {
        key: sum(int(item[key]) for item in file_results)
        for key in (
            "null_rows",
            "mapping_rows",
            "malformed_rows",
            "rows_with_nonempty_bids",
            "rows_with_nonempty_asks",
            "rows_with_both_sides",
            "total_bid_entries",
            "total_ask_entries",
        )
    }
    files_with_nonempty_depth = sum(
        bool(item["total_bid_entries"] or item["total_ask_entries"])
        for item in file_results
    )
    if totals["total_bid_entries"] == 0 and totals["total_ask_entries"] == 0:
        classification = "NESTED_DEPTH_PAYLOAD_EMPTY_ACROSS_COMPLETE_CORPUS"
    else:
        classification = "NESTED_DEPTH_ENTRIES_PRESENT_REQUIRES_EXPLICIT_NORMALIZER"

    summary = {
        "campaign_id": CAMPAIGN_ID,
        "classification": classification,
        "corpus_archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "quote_depth_files": len(file_results),
        "quote_rows": total_rows,
        "files_with_nonempty_depth": files_with_nonempty_depth,
        **totals,
        "normalizer_created": False,
        "strategy_created": False,
        "edge_claim_allowed": False,
        "execution_allowed": False,
    }
    write_json(output / "depth_payload_file_census.json", file_results)
    write_json(output / "depth_payload_census_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--producer-commit", default=os.environ.get("GITHUB_SHA", "UNKNOWN"))
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "run_status.json", {"status": "RUNNING", "campaign_id": CAMPAIGN_ID})
    try:
        run_a = output / "run-a"
        run_b = output / "run-b"
        summary_a = run_census(args.corpus_root.resolve(), run_a)
        summary_b = run_census(args.corpus_root.resolve(), run_b)
        files = ["depth_payload_file_census.json", "depth_payload_census_summary.json"]
        hashes_a = {name: semantic_hash(run_a / name) for name in files}
        hashes_b = {name: semantic_hash(run_b / name) for name in files}
        if summary_a != summary_b or hashes_a != hashes_b:
            raise RuntimeError("two-run full-row depth census determinism failed")
        final = dict(summary_a)
        final.update({"producer_commit": args.producer_commit, "two_run_semantic_determinism": True})
        write_json(output / "depth_payload_census_final_summary.json", final)
        write_json(output / "semantic_determinism_manifest.json", {"classification": "TWO_RUN_SEMANTIC_DETERMINISM_PASSED", "files": hashes_a})
        write_json(output / "run_status.json", {"status": "COMPLETE", "campaign_id": CAMPAIGN_ID, "classification": final["classification"], "producer_commit": args.producer_commit, "two_run_semantic_determinism": True, "execution_allowed": False})
        print(json.dumps(final, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        write_json(output / "run_status.json", {"status": "FAILED", "campaign_id": CAMPAIGN_ID, "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc(), "execution_allowed": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
