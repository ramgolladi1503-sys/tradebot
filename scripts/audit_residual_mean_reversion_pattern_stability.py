#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.residual_liquidity_exhaustion_mr_v2.stability_audit import (
    StabilityAuditContract,
    build_stability_screen,
    summarize_stability_screen,
)

CAMPAIGN_ID = "RESIDUAL_LIQUIDITY_EXHAUSTION_MR_V2"
STAGE = "B_PATTERN_STABILITY_AUDIT"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _load_contract(path: Path) -> tuple[dict[str, Any], StabilityAuditContract]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    contract = StabilityAuditContract(
        horizons_minutes=tuple(int(value) for value in raw["horizons_minutes"]),
        primary_horizons_minutes=tuple(
            int(value) for value in raw["primary_horizons_minutes"]
        ),
        minimum_events=int(raw["minimum_events"]),
        minimum_sessions=int(raw["minimum_sessions"]),
        minimum_calendar_periods=int(raw["minimum_calendar_periods"]),
        minimum_events_per_calendar_period=int(
            raw["minimum_events_per_calendar_period"]
        ),
        sign_flip_permutations=int(raw["sign_flip_permutations"]),
        false_discovery_rate=float(raw["false_discovery_rate"]),
        random_seed=int(raw["random_seed"]),
    )
    contract.validate()
    return raw, contract


def _read_event_ledger(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    if path.suffix in {".jsonl", ".json"}:
        return pd.read_json(path, lines=path.suffix == ".jsonl")
    raise ValueError(f"unsupported event ledger format: {path.suffix}")


def _screen_records(screen: pd.DataFrame) -> list[dict[str, Any]]:
    return [_normalize(row) for row in screen.to_dict(orient="records")]


def _audit_once(
    *,
    ledger_path: Path,
    contract: StabilityAuditContract,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    events = _read_event_ledger(ledger_path)
    screen = build_stability_screen(events, contract=contract)
    summary = summarize_stability_screen(screen, contract=contract)
    summary.update(
        {
            "event_count": int(len(events)),
            "event_ledger_sha256": _sha256(ledger_path),
        }
    )
    return screen, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--event-ledger-a", type=Path, required=True)
    parser.add_argument("--event-ledger-b", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--producer-commit", default=os.environ.get("GITHUB_SHA", "UNKNOWN")
    )
    args = parser.parse_args()

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    _write_json(
        output / "run_status.json",
        {
            "status": "RUNNING",
            "campaign_id": CAMPAIGN_ID,
            "stage": STAGE,
            "producer_commit": args.producer_commit,
            "execution_allowed": False,
        },
    )

    try:
        contract_path = (
            args.project_root.resolve()
            / "research"
            / "residual_liquidity_exhaustion_mr_v2"
            / "stability_audit_contract.json"
        )
        raw_contract, contract = _load_contract(contract_path)
        ledger_a = args.event_ledger_a.resolve()
        ledger_b = args.event_ledger_b.resolve()
        screen_a, summary_a = _audit_once(ledger_path=ledger_a, contract=contract)
        screen_b, summary_b = _audit_once(ledger_path=ledger_b, contract=contract)
        records_a = _screen_records(screen_a)
        records_b = _screen_records(screen_b)
        comparable_a = dict(summary_a)
        comparable_b = dict(summary_b)
        comparable_a.pop("event_ledger_sha256", None)
        comparable_b.pop("event_ledger_sha256", None)
        if records_a != records_b or comparable_a != comparable_b:
            raise RuntimeError(
                "Stage B audit differs across deterministic Stage A ledgers"
            )

        _write_json(output / "frozen_stability_audit_contract.json", raw_contract)
        _write_json(output / "stability_screen.json", records_a)
        pd.DataFrame(records_a).drop(
            columns=["calendar_period_evidence"], errors="ignore"
        ).to_csv(output / "stability_screen.csv", index=False)

        final_summary = dict(summary_a)
        final_summary.update(
            {
                "producer_commit": args.producer_commit,
                "two_ledger_semantic_determinism": True,
                "event_ledger_a_sha256": _sha256(ledger_a),
                "event_ledger_b_sha256": _sha256(ledger_b),
            }
        )
        _write_json(
            output / "stability_audit_final_summary.json", _normalize(final_summary)
        )

        manifest = {
            path.name: _sha256(path)
            for path in sorted(output.iterdir())
            if path.is_file()
            and path.name
            not in {"semantic_determinism_manifest.json", "run_status.json"}
        }
        _write_json(
            output / "semantic_determinism_manifest.json",
            {
                "classification": "TWO_LEDGER_SEMANTIC_DETERMINISM_PASSED",
                "campaign_id": CAMPAIGN_ID,
                "stage": STAGE,
                "producer_commit": args.producer_commit,
                "files": manifest,
            },
        )
        _write_json(
            output / "run_status.json",
            {
                "status": "COMPLETE",
                "campaign_id": CAMPAIGN_ID,
                "stage": STAGE,
                "producer_commit": args.producer_commit,
                "classification": final_summary["classification"],
                "stable_candidate_count": final_summary["stable_candidate_count"],
                "two_ledger_semantic_determinism": True,
                "execution_allowed": False,
            },
        )
        print(json.dumps(_normalize(final_summary), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        _write_json(
            output / "run_status.json",
            {
                "status": "FAILED",
                "campaign_id": CAMPAIGN_ID,
                "stage": STAGE,
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
