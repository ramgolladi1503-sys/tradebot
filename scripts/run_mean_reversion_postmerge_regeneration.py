#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STRATEGY_ID = "MEAN_REVERSION_EXTENSION"
EXPECTED_CORPUS_SHA256 = (
    "8c5fd5cded6475347c94f073b3411d6636c34dcc256243270e23ec8daf6b35f7"
)


def _run(command: list[str], *, cwd: Path) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(path: Path) -> bytes:
    if path.suffix == ".json":
        return json.dumps(
            json.loads(path.read_text(encoding="utf-8")),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    if path.suffix == ".jsonl":
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return "\n".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows
        ).encode()
    return path.read_bytes()


def _semantic_manifest(folder: Path) -> dict[str, str]:
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(_canonical_bytes(path)).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _verify_corpus_and_build_authority(
    *,
    project_root: Path,
    corpus_root: Path,
    manifest_path: Path,
    producer_commit: str,
    output_root: Path,
) -> Path:
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

    actual_files = sorted(path for path in corpus_root.rglob("*.parquet") if path.is_file())
    actual_rel = {path.relative_to(corpus_root).as_posix() for path in actual_files}
    if actual_rel != set(expected):
        raise RuntimeError(
            "corpus inventory mismatch "
            f"missing={sorted(set(expected)-actual_rel)[:20]} "
            f"extra={sorted(actual_rel-set(expected))[:20]}"
        )

    for index, relative in enumerate(sorted(expected), start=1):
        digest = _sha256(corpus_root / relative)
        if digest != expected[relative]:
            raise RuntimeError(f"parquet SHA mismatch: {relative}")
        if index % 250 == 0:
            print(f"verified {index}/{len(expected)} parquet files", flush=True)

    underlying = sorted(corpus_root.glob("*/underlying/*.parquet"))
    if not underlying:
        raise RuntimeError("frozen corpus contains no underlying parquet files")

    dates: set[str] = set()
    symbols: set[str] = set()
    row_counts: list[int] = []
    total_rows = 0
    unsorted_files = 0
    for path in underlying:
        date_key = path.parent.parent.name
        symbol = path.stem.split("_")[0]
        frame = pd.read_parquet(
            path, columns=["timestamp", "open", "high", "low", "close"]
        )
        if frame.empty:
            raise RuntimeError(f"empty underlying parquet: {path}")
        timestamps = pd.to_datetime(frame["timestamp"], errors="raise")
        if timestamps.isna().any():
            raise RuntimeError(f"invalid timestamps: {path}")
        if timestamps.duplicated().any():
            raise RuntimeError(f"duplicate timestamps: {path}")
        if not timestamps.is_monotonic_increasing:
            unsorted_files += 1
        dates.add(date_key)
        symbols.add(symbol)
        row_counts.append(len(frame))
        total_rows += len(frame)

    ordered_dates = sorted(dates)
    uniform_rows = row_counts[0] if len(set(row_counts)) == 1 else None
    base = project_root / "runtime" / "strategy_validation" / STRATEGY_ID
    base.mkdir(parents=True, exist_ok=True)
    audit = {
        "classification": "UPSTOX_CANDLE_FILES_VALID",
        "producer_commit": producer_commit,
        "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
        "manifest_verified": True,
        "parquet_files_verified": len(expected),
        "underlying_symbol_days": len(underlying),
        "underlying_rows": total_rows,
        "symbols": sorted(symbols),
        "first_date": ordered_dates[0],
        "last_date": ordered_dates[-1],
        "source_files_not_monotonic": unsorted_files,
    }
    catalog = {
        "source": "IMMUTABLE_PRIVATE_RELEASE",
        "producer_commit": producer_commit,
        "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
        "date_range_found": ordered_dates,
        "trading_days_count": len(ordered_dates),
        "symbols_found": sorted(symbols),
        "rows_per_day": uniform_rows,
        "underlying_symbol_days": len(underlying),
        "underlying_rows": total_rows,
    }
    _write_json(base / "upstox_candle_file_audit.json", audit)
    _write_json(base / "historical_data_catalog.json", catalog)
    _write_json(output_root / "frozen_input_authority.json", audit)

    prerequisites = output_root / "frozen-prerequisites"
    prerequisites.mkdir(parents=True, exist_ok=True)
    shutil.copy2(base / "upstox_candle_file_audit.json", prerequisites)
    shutil.copy2(base / "historical_data_catalog.json", prerequisites)
    return prerequisites


def _reset_strategy_dir(project_root: Path, prerequisites: Path) -> Path:
    base = project_root / "runtime" / "strategy_validation" / STRATEGY_ID
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)
    for path in prerequisites.glob("*.json"):
        shutil.copy2(path, base / path.name)
    return base


def _run_focused_tests(project_root: Path) -> None:
    _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_phase4_audit_fail_closed.py",
            "tests/test_walk_forward_integrity.py",
            "tests/test_mean_reversion_ledger_integrity.py",
            "tests/test_parameter_discovery_integrity.py",
            "tests/test_tearsheet_oos_metrics.py",
            "tests/test_vectorized_signals_causality.py",
            "tests/test_vertical_slice_metrics.py",
            "tests/test_mean_reversion_ledger_timing.py",
            "tests/test_mean_reversion_ledger_accounting.py",
        ],
        cwd=project_root,
    )


def _run_phase4(
    *, project_root: Path, prerequisites: Path, output_root: Path, label: str
) -> Path:
    base = _reset_strategy_dir(project_root, prerequisites)
    commands = [
        [sys.executable, "scripts/generate_mean_reversion_trade_ledger.py"],
        [
            sys.executable,
            "scripts/audit_mean_reversion_trade_ledger.py",
            "--strategy",
            STRATEGY_ID,
        ],
        [sys.executable, "scripts/audit_phase4_truth.py", "--strategy", STRATEGY_ID],
        [
            sys.executable,
            "scripts/audit_phase4_7_integrity.py",
            "--strategy",
            STRATEGY_ID,
        ],
        [
            sys.executable,
            "scripts/audit_phase4_8_selection_quality.py",
            "--strategy",
            STRATEGY_ID,
        ],
        [
            sys.executable,
            "scripts/audit_phase4_10_accounting.py",
            "--strategy",
            STRATEGY_ID,
        ],
        [
            sys.executable,
            "scripts/audit_phase4_v2_structural.py",
            "--strategy",
            STRATEGY_ID,
        ],
        [sys.executable, "scripts/validate_mean_reversion_vertical_slice.py"],
    ]
    for command in commands:
        _run(command, cwd=project_root)

    target = output_root / label / "phase4"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(base, target)
    return target


def _run_parameter_discovery(
    *, project_root: Path, prerequisites: Path, output_root: Path
) -> dict[str, Any]:
    base = _reset_strategy_dir(project_root, prerequisites)
    _run(
        [
            sys.executable,
            "scripts/run_mean_reversion_parameter_discovery.py",
            "--strategy",
            STRATEGY_ID,
        ],
        cwd=project_root,
    )
    report_path = base / "phase_4_11b_v2_full_grid_report.json"
    if not report_path.exists():
        raise RuntimeError("full-grid parameter discovery did not emit its report")
    target = output_root / "parameter-discovery"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    shutil.copy2(report_path, target / report_path.name)
    shutil.copytree(base, target / "final-runtime-state")
    return _load_json(report_path)


def _combined_nifty_data(corpus_root: Path) -> pd.DataFrame:
    files = sorted(corpus_root.glob("*/underlying/NIFTY_*.parquet"))
    if not files:
        raise RuntimeError("no frozen NIFTY underlying files found")
    frames: list[pd.DataFrame] = []
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    for path in files:
        frame = pd.read_parquet(path)
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise RuntimeError(f"{path} missing columns {missing}")
        frames.append(frame[required].copy())
    data = pd.concat(frames, ignore_index=True)
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="raise")
    data = data.sort_values("timestamp").drop_duplicates("timestamp", keep="first")
    data = data.set_index("timestamp")
    if not data.index.is_monotonic_increasing:
        raise RuntimeError("combined NIFTY data is not monotonic")
    return data


def _run_shared_wfa_twice(
    *, project_root: Path, corpus_root: Path, output_root: Path
) -> dict[str, Any]:
    sys.path.insert(0, str(project_root))
    from scripts.run_walk_forward_elite import run_walk_forward

    data = _combined_nifty_data(corpus_root)
    reports: dict[str, dict[str, Any]] = {}
    for label in ("run-a", "run-b"):
        report = _normalize(run_walk_forward(data.copy(), workers=1))
        reports[label] = report
        folder = output_root / label / "shared-wfa"
        folder.mkdir(parents=True, exist_ok=True)
        _write_json(folder / "certified_wfa_report.json", report)
    if reports["run-a"] != reports["run-b"]:
        raise RuntimeError("shared WFA two-run determinism failed")
    return reports["run-a"]


def _build_final_summary(
    *,
    output_root: Path,
    producer_commit: str,
    discovery: dict[str, Any],
    wfa: dict[str, Any],
) -> dict[str, Any]:
    phase4 = output_root / "run-a" / "phase4"
    report_paths = {
        "phase_4_report": "phase_4_report.json",
        "phase_5_wfa_report": "phase_5_wfa_report.json",
        "ledger_audit": "phase_4_trade_ledger_audit.json",
        "truth_audit": "phase_4_5_truth_audit.json",
        "integrity_audit": "phase_4_7_integrity_audit.json",
        "selection_audit": "phase_4_8_selection_quality_audit.json",
        "accounting_audit": "phase_4_10_accounting_audit.json",
        "structural_audit": "phase_4_v2_structural_audit.json",
    }
    reports = {key: _load_json(phase4 / filename) for key, filename in report_paths.items()}
    phase4_report = reports["phase_4_report"]
    summary = {
        "producer_commit": producer_commit,
        "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
        "phase4_two_run_semantic_determinism": True,
        "shared_wfa_two_run_determinism": True,
        "phase4_verdict": phase4_report.get("verdict"),
        "phase4_passed": phase4_report.get("passed"),
        "phase4_blockers": phase4_report.get("blockers", []),
        "audit_classifications": {
            key: value.get("classification")
            for key, value in reports.items()
            if key.endswith("audit")
        },
        "parameter_discovery_conclusion": discovery.get("conclusion"),
        "parameter_grid_size": discovery.get("executed_grid_size"),
        "train_pass_count": discovery.get("train_pass_count"),
        "validation_pass_count": discovery.get("validation_pass_count"),
        "region_stable_count": discovery.get("region_stable_count"),
        "shared_wfa_status": wfa.get("status"),
        "shared_wfa_promoted": wfa.get("promoted"),
        "shared_wfa_blockers": wfa.get("blockers", []),
        "execution_allowed": False,
        "paper_live_allowed": False,
        "historical_outputs_superseded": True,
        "result_contract": "REGENERATED_RESEARCH_EVIDENCE_ONLY",
    }
    _write_json(output_root / "postmerge_regeneration_summary.json", summary)
    hashes = {
        path.relative_to(output_root).as_posix(): _sha256(path)
        for path in sorted(output_root.rglob("*"))
        if path.is_file() and path.name != "artifact_hash_manifest.json"
    }
    _write_json(
        output_root / "artifact_hash_manifest.json",
        {"producer_commit": producer_commit, "files": hashes},
    )
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
    manifest_path = args.manifest.resolve()
    output_root = args.output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(
        output_root / "run_status.json",
        {
            "status": "RUNNING",
            "producer_commit": args.producer_commit,
            "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
        },
    )

    try:
        prerequisites = _verify_corpus_and_build_authority(
            project_root=project_root,
            corpus_root=corpus_root,
            manifest_path=manifest_path,
            producer_commit=args.producer_commit,
            output_root=output_root,
        )
        _run_focused_tests(project_root)
        run_a = _run_phase4(
            project_root=project_root,
            prerequisites=prerequisites,
            output_root=output_root,
            label="run-a",
        )
        run_b = _run_phase4(
            project_root=project_root,
            prerequisites=prerequisites,
            output_root=output_root,
            label="run-b",
        )
        manifest_a = _semantic_manifest(run_a)
        manifest_b = _semantic_manifest(run_b)
        if manifest_a != manifest_b:
            differing = sorted(
                key
                for key in set(manifest_a) | set(manifest_b)
                if manifest_a.get(key) != manifest_b.get(key)
            )
            raise RuntimeError(f"Phase 4 semantic determinism failed: {differing[:30]}")
        _write_json(
            output_root / "phase4_semantic_hash_manifest.json",
            {
                "producer_commit": args.producer_commit,
                "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
                "two_run_semantic_determinism": True,
                "files": manifest_a,
            },
        )
        discovery = _run_parameter_discovery(
            project_root=project_root,
            prerequisites=prerequisites,
            output_root=output_root,
        )
        wfa = _run_shared_wfa_twice(
            project_root=project_root,
            corpus_root=corpus_root,
            output_root=output_root,
        )
        summary = _build_final_summary(
            output_root=output_root,
            producer_commit=args.producer_commit,
            discovery=discovery,
            wfa=wfa,
        )
        _write_json(
            output_root / "run_status.json",
            {
                "status": "COMPLETE",
                "producer_commit": args.producer_commit,
                "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
                "summary": summary,
            },
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        _write_json(
            output_root / "run_status.json",
            {
                "status": "FAILED",
                "producer_commit": args.producer_commit,
                "corpus_archive_sha256": EXPECTED_CORPUS_SHA256,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
