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
    RESEARCH_APPLEDOUBLE_METADATA,
    RESEARCH_CANDLE,
    RESEARCH_NON_CANDLE_QUOTE,
    load_research_candle_parquet,
)
from research.liquidity_exhaustion_depth_readiness_v2.depth_readiness import (
    DepthReadinessContract,
    audit_quote_frame,
    summarize_depth_readiness,
)


CAMPAIGN_ID = "LIQUIDITY_EXHAUSTION_DEPTH_READINESS_V2"
EXPECTED_ARCHIVE_SHA256 = "8c5fd5cded6475347c94f073b3411d6636c34dcc256243270e23ec8daf6b35f7"
EXPECTED_REAL_FILES = 1676
EXPECTED_QUOTE_FILES = 129


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_contract(project_root: Path) -> tuple[dict[str, Any], DepthReadinessContract]:
    path = (
        project_root
        / "research"
        / "liquidity_exhaustion_depth_readiness_v2"
        / "contract.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    contract = DepthReadinessContract(
        minimum_development_sessions=int(raw["minimum_development_sessions"]),
        minimum_future_holdout_sessions=int(raw["minimum_future_holdout_sessions"]),
        minimum_session_span_minutes=float(raw["minimum_session_span_minutes"]),
        maximum_median_gap_seconds=float(raw["maximum_median_gap_seconds"]),
        maximum_p95_gap_seconds=float(raw["maximum_p95_gap_seconds"]),
        maximum_crossed_market_rate=float(raw["maximum_crossed_market_rate"]),
        requires_bid_and_ask_size_or_structured_depth=bool(
            raw["requires_bid_and_ask_size_or_structured_depth"]
        ),
    )
    contract.validate()
    return raw, contract


def _verify_manifest(corpus_root: Path, manifest_path: Path) -> dict[str, str]:
    marker = "/runtime/upstox_candidate_replay/"
    expected: dict[str, str] = {}
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        digest, original = raw.split(maxsplit=1)
        if marker not in original:
            raise RuntimeError(f"manifest path lacks authority marker: {original}")
        relative = original.split(marker, 1)[1].strip()
        expected[relative] = digest.lower()
    if len(expected) != EXPECTED_REAL_FILES:
        raise RuntimeError(f"unexpected manifest file count: {len(expected)}")

    actual = {
        path.relative_to(corpus_root).as_posix()
        for path in corpus_root.rglob("*.parquet")
        if path.is_file() and not path.name.startswith("._")
    }
    if actual != set(expected):
        raise RuntimeError("corpus real-file inventory differs from manifest")
    for index, relative in enumerate(sorted(expected), start=1):
        if _sha256(corpus_root / relative) != expected[relative]:
            raise RuntimeError(f"parquet digest mismatch: {relative}")
        if index % 250 == 0:
            print(f"verified {index}/{len(expected)} real parquet files", flush=True)
    return expected


def _collect_audits(corpus_root: Path) -> tuple[list[dict[str, Any]], set[str], dict[str, int]]:
    audits: list[dict[str, Any]] = []
    candle_dates: set[str] = set()
    counts = {"candle_files": 0, "quote_depth_files": 0, "appledouble_files": 0}
    for path in sorted(corpus_root.glob("*/underlying/*.parquet")):
        date_key = path.parent.parent.name
        classification, frame, _ = load_research_candle_parquet(path)
        if classification == RESEARCH_APPLEDOUBLE_METADATA:
            counts["appledouble_files"] += 1
            continue
        if classification == RESEARCH_CANDLE:
            counts["candle_files"] += 1
            candle_dates.add(date_key)
            continue
        if classification != RESEARCH_NON_CANDLE_QUOTE:
            raise RuntimeError(f"unexpected classification for {path}: {classification}")
        counts["quote_depth_files"] += 1
        quote_frame = pd.read_parquet(path)
        audits.append(
            audit_quote_frame(
                quote_frame,
                source=path.relative_to(corpus_root).as_posix(),
                date_key=date_key,
            )
        )
    if counts["quote_depth_files"] != EXPECTED_QUOTE_FILES:
        raise RuntimeError(f"unexpected quote/depth count: {counts}")
    return audits, candle_dates, counts


def _semantic_hash(path: Path) -> str:
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    elif path.suffix == ".csv":
        data = pd.read_csv(path).to_csv(index=False).encode()
    else:
        data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _run_once(
    *,
    corpus_root: Path,
    contract: DepthReadinessContract,
    target: Path,
) -> dict[str, Any]:
    target.mkdir(parents=True, exist_ok=True)
    audits, candle_dates, counts = _collect_audits(corpus_root)
    summary = summarize_depth_readiness(audits, candle_dates=candle_dates, contract=contract)
    summary["campaign_id"] = CAMPAIGN_ID
    summary["corpus_archive_sha256"] = EXPECTED_ARCHIVE_SHA256
    summary["classification_counts"] = counts

    flat_rows = []
    for item in audits:
        row = {key: value for key, value in item.items() if key not in {"columns", "symbols", "tokens", "depth_capability"}}
        row["columns"] = "|".join(item["columns"])
        row["symbols"] = "|".join(item["symbols"])
        row["tokens"] = "|".join(item["tokens"])
        row["supports_imbalance_or_replenishment"] = item["depth_capability"][
            "supports_imbalance_or_replenishment"
        ]
        flat_rows.append(row)
    pd.DataFrame(flat_rows).sort_values("source", kind="mergesort").to_csv(
        target / "depth_file_inventory.csv", index=False
    )
    _write_json(target / "depth_file_audits.json", audits)
    _write_json(target / "depth_readiness_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--producer-commit", default=os.environ.get("GITHUB_SHA", "UNKNOWN"))
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    corpus_root = args.corpus_root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _write_json(output / "run_status.json", {"status": "RUNNING", "campaign_id": CAMPAIGN_ID})

    try:
        raw_contract, contract = _load_contract(project_root)
        manifest = _verify_manifest(corpus_root, args.manifest.resolve())
        _write_json(output / "frozen_contract.json", raw_contract)
        _write_json(
            output / "input_authority.json",
            {
                "classification": "DEPTH_READINESS_INPUT_AUTHORITY_VALID",
                "campaign_id": CAMPAIGN_ID,
                "producer_commit": args.producer_commit,
                "corpus_archive_sha256": EXPECTED_ARCHIVE_SHA256,
                "manifest_files_verified": len(manifest),
            },
        )

        run_a = output / "run-a"
        run_b = output / "run-b"
        summary_a = _run_once(corpus_root=corpus_root, contract=contract, target=run_a)
        summary_b = _run_once(corpus_root=corpus_root, contract=contract, target=run_b)
        files = ["depth_file_inventory.csv", "depth_file_audits.json", "depth_readiness_summary.json"]
        hashes_a = {name: _semantic_hash(run_a / name) for name in files}
        hashes_b = {name: _semantic_hash(run_b / name) for name in files}
        if summary_a != summary_b or hashes_a != hashes_b:
            raise RuntimeError("two-run depth readiness determinism failed")

        final = dict(summary_a)
        final.update(
            {
                "producer_commit": args.producer_commit,
                "two_run_semantic_determinism": True,
            }
        )
        _write_json(output / "depth_readiness_final_summary.json", final)
        _write_json(
            output / "semantic_determinism_manifest.json",
            {
                "classification": "TWO_RUN_SEMANTIC_DETERMINISM_PASSED",
                "campaign_id": CAMPAIGN_ID,
                "files": hashes_a,
            },
        )
        _write_json(
            output / "run_status.json",
            {
                "status": "COMPLETE",
                "campaign_id": CAMPAIGN_ID,
                "classification": final["classification"],
                "producer_commit": args.producer_commit,
                "two_run_semantic_determinism": True,
                "execution_allowed": False,
            },
        )
        print(json.dumps(final, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        _write_json(
            output / "run_status.json",
            {
                "status": "FAILED",
                "campaign_id": CAMPAIGN_ID,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "execution_allowed": False,
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
