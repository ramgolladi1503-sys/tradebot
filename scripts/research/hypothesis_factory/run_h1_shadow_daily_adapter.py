#!/usr/bin/env python3
"""Run H1 no-order shadow adapter, validator, and observer.

This wrapper is intentionally data/read-only. It accepts existing raw Kite CSV
and/or already-normalised H1 completed-bar CSVs, writes a V19-compatible input
file, runs the existing hardened validator, and then runs the existing H1
prospective observer. It never requests order, broker write, paper, or live
authority.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.hypothesis_factory.h1_shadow_adapter import (
    CANDIDATE_ID,
    H1ShadowAdapterConfig,
    NoOrderShadowAuthority,
    build_shadow_run_id,
    merge_h1_completed_bar_csvs,
    normalise_kite_intraday_csv,
    write_json,
)


def _default_h1_bars_path(observation_date: str) -> Path:
    return (
        REPO_ROOT
        / "research"
        / "evidence"
        / "trapped_push_snapback_v18_today_readonly_fetch"
        / "input_bars"
        / f"NIFTY_5MIN_{observation_date}_COMPLETED.csv"
    )


def _default_evidence_root(observation_date: str) -> Path:
    return (
        REPO_ROOT
        / "research"
        / "evidence"
        / "h1_shadow_daily_adapter_v1"
        / observation_date.replace("-", "")
    )


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command_redacted": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def run_shadow_adapter(args: argparse.Namespace) -> dict[str, Any]:
    authority = NoOrderShadowAuthority(
        paper_authorized=False,
        live_authorized=False,
        order_authority=False,
        broker_write_authority=False,
    )
    authority.assert_safe()

    config = H1ShadowAdapterConfig(
        observation_date=args.observation_date,
        keep_start=args.keep_start,
        opening_start=args.opening_start,
        opening_end=args.opening_end,
        keep_end=args.keep_end,
        source_label=args.source_label,
    )
    config.validate()

    evidence_root = Path(args.evidence_root) if args.evidence_root else _default_evidence_root(args.observation_date)
    h1_bars_output = Path(args.h1_bars_output) if args.h1_bars_output else _default_h1_bars_path(args.observation_date)
    evidence_root.mkdir(parents=True, exist_ok=True)

    normalized_inputs: list[Path] = []
    normalization_reports: list[dict[str, Any]] = []

    for index, raw_csv in enumerate(args.raw_kite_csv or []):
        normalized_path = evidence_root / "normalized_inputs" / f"raw_kite_{index:02d}_h1_completed.csv"
        report = normalise_kite_intraday_csv(
            raw_csv,
            normalized_path,
            config,
            authority=authority,
        )
        normalized_inputs.append(normalized_path)
        normalization_reports.append(report)

    for completed_csv in args.completed_h1_csv or []:
        normalized_inputs.append(Path(completed_csv))

    if not normalized_inputs:
        raise ValueError("Provide at least one --raw-kite-csv or --completed-h1-csv")

    merge_report = merge_h1_completed_bar_csvs(
        normalized_inputs,
        h1_bars_output,
        config,
        authority=authority,
    )

    validation_audit = evidence_root / "INPUT_BAR_VALIDATION_AUDIT.json"
    validator_command = [
        sys.executable,
        "scripts/research/hypothesis_factory/validate_h1_forward_bar_intake_v18.py",
        "--input-bars",
        str(h1_bars_output),
        "--output-audit",
        str(validation_audit),
        "--observation-date",
        args.observation_date,
        "--opening-start",
        args.opening_start,
        "--opening-end",
        args.opening_end,
    ]

    observer_root = evidence_root / "runs"
    run_id = args.run_id or build_shadow_run_id(args.observation_date, prefix="KITE_H1_SHADOW")
    observer_command = [
        sys.executable,
        "scripts/research/hypothesis_factory/run_trapped_push_snapback_v14_prospective_observer.py",
        "--mode",
        "manual_append",
        "--input-bars",
        str(h1_bars_output),
        "--output-root",
        str(observer_root),
        "--run-id",
        run_id,
        "--candidate-id",
        CANDIDATE_ID,
        "--opening-start",
        args.opening_start,
        "--opening-end",
        args.opening_end,
        "--evidence-commit",
        args.evidence_commit,
        "--registry-commit",
        args.registry_commit,
    ]

    validation_result: dict[str, Any] | None = None
    observer_result: dict[str, Any] | None = None

    if not args.normalise_only:
        validation_result = _run_command(validator_command, cwd=REPO_ROOT)
        if validation_result["returncode"] == 0:
            observer_result = _run_command(observer_command, cwd=REPO_ROOT)
        else:
            observer_result = {
                "command_redacted": observer_command,
                "returncode": None,
                "stdout_tail": "",
                "stderr_tail": "Observer skipped because validation failed.",
            }

    audit = {
        "schema_version": "H1_SHADOW_DAILY_ADAPTER_RUN_AUDIT_V1",
        "candidate_id": CANDIDATE_ID,
        "observation_date": args.observation_date,
        "h1_bars_output": str(h1_bars_output),
        "evidence_root": str(evidence_root),
        "run_id": run_id,
        "normalization_reports": normalization_reports,
        "merge_report": merge_report,
        "validation_result": validation_result,
        "observer_result": observer_result,
        "orders_created": 0,
        "broker_writes_created": 0,
        "paper_authorized": False,
        "live_authorized": False,
        "order_authority": False,
        "broker_write_authority": False,
        "predicate_changed": False,
        "controlled_status": (
            "H1_SHADOW_ADAPTER_NORMALISED_ONLY"
            if args.normalise_only
            else (
                "H1_SHADOW_ADAPTER_RUN_COMPLETE"
                if validation_result and validation_result.get("returncode") == 0 and observer_result and observer_result.get("returncode") == 0
                else "H1_SHADOW_ADAPTER_BLOCKED"
            )
        ),
    }
    write_json(evidence_root / "H1_SHADOW_ADAPTER_RUN_AUDIT.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description="H1 no-order shadow data adapter and daily runner")
    parser.add_argument("--observation-date", required=True, help="YYYY-MM-DD market date in Asia/Kolkata")
    parser.add_argument("--raw-kite-csv", action="append", default=[], help="Raw Kite fetch CSV; may be repeated")
    parser.add_argument("--completed-h1-csv", action="append", default=[], help="Already-normalised H1 completed-bar CSV; may be repeated")
    parser.add_argument("--h1-bars-output", default="", help="Output completed-bar CSV path")
    parser.add_argument("--evidence-root", default="", help="Evidence root for audits and observer run")
    parser.add_argument("--run-id", default="", help="Observer run id")
    parser.add_argument("--opening-start", default="09:15")
    parser.add_argument("--opening-end", default="11:30")
    parser.add_argument("--keep-start", default="09:15")
    parser.add_argument("--keep-end", default="12:00")
    parser.add_argument("--source-label", default="KITE_HISTORICAL_READ_ONLY")
    parser.add_argument("--evidence-commit", required=True)
    parser.add_argument("--registry-commit", default="b57197b5643b0e99087dbfac091eb9a2054a5e1b")
    parser.add_argument("--normalise-only", action="store_true")
    args = parser.parse_args()

    audit = run_shadow_adapter(args)
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["controlled_status"] != "H1_SHADOW_ADAPTER_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
