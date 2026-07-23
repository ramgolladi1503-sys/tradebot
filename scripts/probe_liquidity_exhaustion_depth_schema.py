#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from core.research_backtest_integrity import (
    RESEARCH_NON_CANDLE_QUOTE,
    load_research_candle_parquet,
)
from research.liquidity_exhaustion_depth_schema_v2.schema_probe import inspect_depth_series

CAMPAIGN_ID = "LIQUIDITY_EXHAUSTION_DEPTH_SCHEMA_V2"
EXPECTED_ARCHIVE_SHA256 = "8c5fd5cded6475347c94f073b3411d6636c34dcc256243270e23ec8daf6b35f7"
EXPECTED_QUOTE_FILES = 129


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def semantic_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def run_probe(corpus_root: Path, output: Path) -> dict[str, Any]:
    file_results: list[dict[str, Any]] = []
    signature_files: defaultdict[str, int] = defaultdict(int)
    path_file_coverage: Counter[str] = Counter()
    price_keys: Counter[str] = Counter()
    size_keys: Counter[str] = Counter()

    quote_paths: list[Path] = []
    for path in sorted(corpus_root.glob("*/underlying/*.parquet")):
        classification, _, _ = load_research_candle_parquet(path)
        if classification == RESEARCH_NON_CANDLE_QUOTE:
            quote_paths.append(path)
    if len(quote_paths) != EXPECTED_QUOTE_FILES:
        raise RuntimeError(f"expected {EXPECTED_QUOTE_FILES} quote files, found {len(quote_paths)}")

    for index, path in enumerate(quote_paths, start=1):
        frame = pd.read_parquet(path, columns=["ts", "token", "symbol", "ltp", "bid", "ask", "depth"])
        result = inspect_depth_series(frame["depth"])
        result.update(
            {
                "source": path.relative_to(corpus_root).as_posix(),
                "symbol": str(frame["symbol"].dropna().iloc[0]),
                "token": str(frame["token"].dropna().iloc[0]),
                "top_level_bid_nonzero_count": int((pd.to_numeric(frame["bid"], errors="coerce") > 0).sum()),
                "top_level_ask_nonzero_count": int((pd.to_numeric(frame["ask"], errors="coerce") > 0).sum()),
                "top_level_ltp_nonzero_count": int((pd.to_numeric(frame["ltp"], errors="coerce") > 0).sum()),
            }
        )
        file_results.append(result)
        if result["dominant_signature"]:
            signature_files[result["dominant_signature"]] += 1
        for path_type in result["path_type_counts"]:
            path_file_coverage[path_type] += 1
        for key in result["price_like_keys"]:
            price_keys[key] += 1
        for key in result["size_like_keys"]:
            size_keys[key] += 1
        if index % 25 == 0:
            print(f"probed {index}/{len(quote_paths)} depth files", flush=True)

    summary = {
        "campaign_id": CAMPAIGN_ID,
        "classification": "NESTED_DEPTH_SCHEMA_PROBED_NO_NORMALIZATION_CLAIM",
        "corpus_archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "quote_depth_files": len(file_results),
        "dominant_signature_file_counts": dict(sorted(signature_files.items())),
        "path_file_coverage": dict(sorted(path_file_coverage.items())),
        "price_like_key_file_counts": dict(sorted(price_keys.items())),
        "size_like_key_file_counts": dict(sorted(size_keys.items())),
        "all_files_have_one_dominant_signature": len(signature_files) == 1,
        "strategy_created": False,
        "normalizer_created": False,
        "edge_claim_allowed": False,
        "execution_allowed": False,
    }
    write_json(output / "depth_schema_file_results.json", file_results)
    write_json(output / "depth_schema_summary.json", summary)
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
        summary_a = run_probe(args.corpus_root.resolve(), run_a)
        summary_b = run_probe(args.corpus_root.resolve(), run_b)
        files = ["depth_schema_file_results.json", "depth_schema_summary.json"]
        hashes_a = {name: semantic_hash(run_a / name) for name in files}
        hashes_b = {name: semantic_hash(run_b / name) for name in files}
        if summary_a != summary_b or hashes_a != hashes_b:
            raise RuntimeError("two-run nested-depth schema determinism failed")
        final = dict(summary_a)
        final.update({"producer_commit": args.producer_commit, "two_run_semantic_determinism": True})
        write_json(output / "depth_schema_final_summary.json", final)
        write_json(output / "semantic_determinism_manifest.json", {"classification": "TWO_RUN_SEMANTIC_DETERMINISM_PASSED", "files": hashes_a})
        write_json(output / "run_status.json", {"status": "COMPLETE", "campaign_id": CAMPAIGN_ID, "classification": final["classification"], "producer_commit": args.producer_commit, "two_run_semantic_determinism": True, "execution_allowed": False})
        print(json.dumps(final, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        write_json(output / "run_status.json", {"status": "FAILED", "campaign_id": CAMPAIGN_ID, "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc(), "execution_allowed": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
