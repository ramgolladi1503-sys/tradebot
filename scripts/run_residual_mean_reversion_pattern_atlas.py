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

import numpy as np
import pandas as pd

from core.research_backtest_integrity import (
    RESEARCH_APPLEDOUBLE_METADATA,
    RESEARCH_CANDLE,
    RESEARCH_NON_CANDLE_QUOTE,
    load_research_candle_parquet,
)
from research.residual_liquidity_exhaustion_mr_v2.pattern_atlas import (
    CANONICAL_SYMBOL_ALIASES,
    PatternAtlasContract,
    build_residual_panel,
    build_segment_metrics,
    canonicalize_symbol,
    extract_residual_events,
    permutation_control,
)


CAMPAIGN_ID = "RESIDUAL_LIQUIDITY_EXHAUSTION_MR_V2"
EXPECTED_ARCHIVE_SHA256 = "8c5fd5cded6475347c94f073b3411d6636c34dcc256243270e23ec8daf6b35f7"
EXPECTED_CANDLE_FILES = 1547
EXPECTED_QUOTE_FILES = 129
EXPECTED_APPLEDOUBLE_FILES = 1676


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_contract(project_root: Path) -> tuple[dict[str, Any], PatternAtlasContract]:
    path = (
        project_root
        / "research"
        / "residual_liquidity_exhaustion_mr_v2"
        / "contract.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    frozen = raw["frozen_corpus"]
    if frozen["archive_sha256"] != EXPECTED_ARCHIVE_SHA256:
        raise RuntimeError("contract archive hash does not match executable authority")
    if int(frozen["expected_candle_files"]) != EXPECTED_CANDLE_FILES:
        raise RuntimeError("contract candle count does not match executable authority")
    if int(frozen["expected_quote_depth_files"]) != EXPECTED_QUOTE_FILES:
        raise RuntimeError("contract quote count does not match executable authority")
    if int(frozen["expected_appledouble_files"]) != EXPECTED_APPLEDOUBLE_FILES:
        raise RuntimeError("contract AppleDouble count does not match executable authority")

    confirmation = raw["confirmation"]
    control = raw["negative_control"]
    contract = PatternAtlasContract(
        bar_minutes=int(raw["bar_minutes"]),
        volatility_window_bars=int(raw["volatility_window_bars"]),
        volatility_min_periods=int(raw["volatility_min_periods"]),
        residual_threshold=float(raw["event_threshold_abs_residual_z"]),
        contraction_ratio=float(confirmation["maximum_residual_contraction_ratio"]),
        max_extension_fraction=float(
            confirmation["maximum_continuation_extension_fraction_of_event_range"]
        ),
        horizons_minutes=tuple(int(value) for value in raw["outcome_horizons_minutes"]),
        permutation_count=int(control["permutations"]),
        random_seed=int(control["seed"]),
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
        if relative in expected:
            raise RuntimeError(f"duplicate manifest path: {relative}")
        expected[relative] = digest.lower()

    real_files = sorted(
        path
        for path in corpus_root.rglob("*.parquet")
        if path.is_file() and not path.name.startswith("._")
    )
    actual = {path.relative_to(corpus_root).as_posix() for path in real_files}
    if actual != set(expected):
        raise RuntimeError(
            "manifest inventory mismatch "
            f"missing={sorted(set(expected) - actual)[:20]} "
            f"extra={sorted(actual - set(expected))[:20]}"
        )

    for index, relative in enumerate(sorted(expected), start=1):
        if _sha256(corpus_root / relative) != expected[relative]:
            raise RuntimeError(f"manifest digest mismatch: {relative}")
        if index % 250 == 0:
            print(f"verified {index}/{len(expected)} real parquet files", flush=True)
    return expected


def _assert_one_session(frame: pd.DataFrame, *, date_key: str, path: Path) -> None:
    timestamps = pd.to_datetime(frame["timestamp"], errors="raise")
    observed = {
        pd.Timestamp(value).strftime("%Y%m%d")
        for value in timestamps.dt.normalize().unique()
    }
    if observed != {date_key}:
        raise RuntimeError(
            f"candle session/date mismatch path={path} expected={date_key} observed={sorted(observed)}"
        )


def _frames_equivalent(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    common = [column for column in columns if column in left.columns and column in right.columns]
    if common != [column for column in columns if column in left.columns]:
        return False
    left_norm = left[common].sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    right_norm = right[common].sort_values("timestamp", kind="mergesort").reset_index(drop=True)
    if left_norm.shape != right_norm.shape:
        return False
    return bool(left_norm.equals(right_norm))


def _load_corpus(
    corpus_root: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], dict[str, Any]]:
    candle_parts: dict[str, list[pd.DataFrame]] = defaultdict(list)
    per_session: dict[tuple[str, str], tuple[pd.DataFrame, Path, str]] = {}
    raw_symbol_counts: Counter[str] = Counter()
    canonical_counts: Counter[str] = Counter()
    quote_dates: Counter[str] = Counter()
    quote_schema_counts: Counter[str] = Counter()
    appledouble_count = 0
    candle_count = 0
    quote_count = 0
    candle_rows = 0

    files = sorted(corpus_root.glob("*/underlying/*.parquet"))
    if not files:
        raise RuntimeError("frozen corpus contains no underlying parquet files")

    for path in files:
        date_key = path.parent.parent.name
        classification, frame, raw_symbol = load_research_candle_parquet(path)
        if classification == RESEARCH_APPLEDOUBLE_METADATA:
            appledouble_count += 1
            continue
        if classification == RESEARCH_NON_CANDLE_QUOTE:
            quote_count += 1
            quote_dates[date_key] += 1
            schema = tuple(sorted(str(column) for column in pd.read_parquet(path).columns))
            quote_schema_counts[hashlib.sha256(repr(schema).encode()).hexdigest()[:16]] += 1
            continue
        if classification != RESEARCH_CANDLE or frame is None or raw_symbol is None:
            raise RuntimeError(
                f"unexpected research classification path={path} classification={classification}"
            )
        if raw_symbol not in CANONICAL_SYMBOL_ALIASES:
            raise RuntimeError(f"unsupported candle symbol path={path} symbol={raw_symbol}")
        _assert_one_session(frame, date_key=date_key, path=path)
        canonical = canonicalize_symbol(raw_symbol)
        candle_count += 1
        candle_rows += len(frame)
        raw_symbol_counts[raw_symbol] += 1
        canonical_counts[canonical] += 1
        key = (date_key, canonical)
        if key in per_session:
            existing, existing_path, existing_raw = per_session[key]
            if not _frames_equivalent(existing, frame):
                raise RuntimeError(
                    "conflicting canonical alias files "
                    f"date={date_key} canonical={canonical} "
                    f"left={existing_path}:{existing_raw} right={path}:{raw_symbol}"
                )
            continue
        per_session[key] = (frame, path, raw_symbol)
        candle_parts[canonical].append(frame)

    counts = {
        "candle_files": candle_count,
        "quote_depth_files": quote_count,
        "appledouble_files": appledouble_count,
    }
    expected = {
        "candle_files": EXPECTED_CANDLE_FILES,
        "quote_depth_files": EXPECTED_QUOTE_FILES,
        "appledouble_files": EXPECTED_APPLEDOUBLE_FILES,
    }
    if counts != expected:
        raise RuntimeError(f"frozen classification mismatch expected={expected} actual={counts}")

    required = {"NIFTY", "BANKNIFTY", "SENSEX"}
    if set(candle_parts) != required:
        raise RuntimeError(
            f"canonical index universe mismatch expected={sorted(required)} actual={sorted(candle_parts)}"
        )

    combined: dict[str, pd.DataFrame] = {}
    for symbol, frames in sorted(candle_parts.items()):
        data = pd.concat(frames, ignore_index=True)
        data = data.sort_values("timestamp", kind="mergesort").reset_index(drop=True)
        if data["timestamp"].duplicated().any():
            raise RuntimeError(f"duplicate timestamps across sessions for {symbol}")
        combined[symbol] = data

    authority = {
        "classification": "RESIDUAL_PATTERN_ATLAS_INPUT_AUTHORITY_VALID",
        "campaign_id": CAMPAIGN_ID,
        "corpus_archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "underlying_files_classified": len(files),
        "candle_files": candle_count,
        "quote_depth_files": quote_count,
        "appledouble_files": appledouble_count,
        "candle_rows": candle_rows,
        "raw_symbol_file_counts": dict(sorted(raw_symbol_counts.items())),
        "canonical_symbol_file_counts": dict(sorted(canonical_counts.items())),
        "canonical_session_counts": dict(
            sorted(Counter(symbol for _, symbol in per_session).items())
        ),
        "first_date": min(key[0] for key in per_session),
        "last_date": max(key[0] for key in per_session),
    }
    quote_coverage = {
        "classification": "QUOTE_DEPTH_COVERAGE_INVENTORIED_NOT_USED_FOR_SIGNALS",
        "campaign_id": CAMPAIGN_ID,
        "quote_depth_files": quote_count,
        "dates_with_quote_depth": len(quote_dates),
        "files_by_date": dict(sorted(quote_dates.items())),
        "schema_hash_counts": dict(sorted(quote_schema_counts.items())),
        "signal_claim_allowed": False,
        "reason": "Stage A is candle residual discovery; quote/depth coverage is not yet synchronized into a causal exhaustion event contract.",
    }
    return combined, authority, quote_coverage


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _run_once(
    *,
    frames: dict[str, pd.DataFrame],
    contract: PatternAtlasContract,
    target: Path,
) -> dict[str, Any]:
    target.mkdir(parents=True, exist_ok=True)
    panel = build_residual_panel(frames, contract=contract)
    events = extract_residual_events(panel, contract=contract)
    if events.empty:
        raise RuntimeError("frozen residual atlas emitted no extreme events")
    segments = build_segment_metrics(events, contract=contract)
    controls = {
        f"{horizon}m": permutation_control(
            events,
            horizon_minutes=horizon,
            contract=contract,
        )
        for horizon in contract.horizons_minutes
    }

    events.to_parquet(target / "residual_event_ledger.parquet", index=False)
    events.to_json(
        target / "residual_event_ledger.jsonl",
        orient="records",
        lines=True,
        date_format="iso",
    )
    segments.to_csv(target / "residual_segment_metrics.csv", index=False)
    _write_json(target / "negative_controls.json", _normalize_json(controls))

    overall = segments.loc[segments["dimension"] == "overall"].iloc[0].to_dict()
    summary = {
        "classification": "PATTERN_ATLAS_COMPLETE_DEVELOPMENT_ONLY",
        "campaign_id": CAMPAIGN_ID,
        "event_count": int(len(events)),
        "overall": _normalize_json(overall),
        "negative_controls": _normalize_json(controls),
        "strategy_created": False,
        "structural_edge_claim_allowed": False,
        "profitability_claim_allowed": False,
        "paper_live_allowed": False,
        "execution_allowed": False,
        "next_gate": "REVIEW_PATTERN_STABILITY_AND_FREEZE_A_SEPARATE_V2_SIGNAL_EQUATION_BEFORE_BACKTESTING",
    }
    _write_json(target / "pattern_atlas_summary.json", summary)
    return summary


def _semantic_manifest(folder: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(folder).as_posix()
        if path.suffix == ".json":
            canonical = json.dumps(
                json.loads(path.read_text(encoding="utf-8")),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        elif path.suffix == ".jsonl":
            rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            canonical = "\n".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows
            ).encode()
        elif path.suffix == ".csv":
            canonical = pd.read_csv(path).to_csv(index=False).encode()
        else:
            canonical = path.read_bytes()
        hashes[relative] = hashlib.sha256(canonical).hexdigest()
    return hashes


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
    _write_json(
        output / "run_status.json",
        {
            "status": "RUNNING",
            "campaign_id": CAMPAIGN_ID,
            "producer_commit": args.producer_commit,
            "execution_allowed": False,
        },
    )

    try:
        raw_contract, contract = _load_contract(project_root)
        manifest = _verify_manifest(corpus_root, args.manifest.resolve())
        frames, authority, quote_coverage = _load_corpus(corpus_root)
        authority["manifest_files_verified"] = len(manifest)
        authority["producer_commit"] = args.producer_commit
        _write_json(output / "input_authority.json", authority)
        _write_json(output / "quote_depth_coverage.json", quote_coverage)
        _write_json(output / "frozen_contract.json", raw_contract)

        run_a = output / "run-a"
        run_b = output / "run-b"
        summary_a = _run_once(frames=frames, contract=contract, target=run_a)
        summary_b = _run_once(frames=frames, contract=contract, target=run_b)
        manifest_a = _semantic_manifest(run_a)
        manifest_b = _semantic_manifest(run_b)
        if manifest_a != manifest_b or summary_a != summary_b:
            differing = sorted(
                key
                for key in set(manifest_a) | set(manifest_b)
                if manifest_a.get(key) != manifest_b.get(key)
            )
            raise RuntimeError(f"two-run semantic determinism failed: {differing[:30]}")

        _write_json(
            output / "semantic_determinism_manifest.json",
            {
                "classification": "TWO_RUN_SEMANTIC_DETERMINISM_PASSED",
                "campaign_id": CAMPAIGN_ID,
                "producer_commit": args.producer_commit,
                "files": manifest_a,
            },
        )
        final_summary = dict(summary_a)
        final_summary.update(
            {
                "producer_commit": args.producer_commit,
                "corpus_archive_sha256": EXPECTED_ARCHIVE_SHA256,
                "two_run_semantic_determinism": True,
                "input_authority": authority,
                "quote_depth_lane": quote_coverage["classification"],
            }
        )
        _write_json(output / "pattern_atlas_final_summary.json", final_summary)
        _write_json(
            output / "run_status.json",
            {
                "status": "COMPLETE",
                "campaign_id": CAMPAIGN_ID,
                "producer_commit": args.producer_commit,
                "classification": final_summary["classification"],
                "event_count": final_summary["event_count"],
                "two_run_semantic_determinism": True,
                "execution_allowed": False,
            },
        )
        print(json.dumps(final_summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        _write_json(
            output / "run_status.json",
            {
                "status": "FAILED",
                "campaign_id": CAMPAIGN_ID,
                "producer_commit": args.producer_commit,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "execution_allowed": False,
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
