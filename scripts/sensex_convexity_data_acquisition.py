#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.sensex_late_session_convexity_v1.data_acquisition import (
    CAMPAIGN,
    KITE_LIMITATION_FINDINGS,
    build_frozen_spec,
    build_readiness_report,
    credential_status,
    inventory_sources,
    recover_option_registry,
    write_json,
)


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _default_roots() -> list[Path]:
    return [
        REPO_ROOT / "runtime",
        REPO_ROOT / "data",
        Path("/Users/madhuram/tradebot-ml-evidence/all-strategy-option-pf-v1"),
        Path("/Users/madhuram/tradebot-ml-evidence/ce-pe-option-certification-v1"),
        Path("/Users/madhuram/tradebot-ml-evidence/corpus-upload"),
    ]


def _latest_completed_trade_date() -> str:
    now_ist = pd.Timestamp.now(tz="Asia/Kolkata")
    day = now_ist.date()
    if now_ist.time() <= pd.Timestamp("15:45").time():
        day = day - timedelta(days=1)
    while day.weekday() >= 5:
        day = day - timedelta(days=1)
    return day.isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SENSEX convexity data acquisition inventory and readiness bundle.")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "research" / "sensex_late_session_convexity_v1"))
    parser.add_argument("--evidence-root", default=f"/Users/madhuram/tradebot-ml-evidence/{CAMPAIGN}")
    args = parser.parse_args(argv)

    output_dir = Path(args.output_dir).resolve()
    evidence_root = Path(args.evidence_root).resolve()
    for rel in ("raw/instrument_master", "raw/underlying", "raw/constituents", "raw/futures", "raw/options", "canonical/minute", "canonical/five_minute", "manifests", "audits", "reports"):
        (evidence_root / rel).mkdir(parents=True, exist_ok=True)

    start_timestamp = pd.Timestamp.now(tz="Asia/Kolkata").isoformat()
    source_commit = _git(["rev-parse", "HEAD"])
    source_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    python_version = sys.version.split()[0]

    pre_change = {
        "source_branch": source_branch,
        "source_commit": source_commit,
        "worktree_path": str(REPO_ROOT),
        "python_version": python_version,
        "dependency_state": "not pinned by this acquisition script",
        "start_timestamp_ist": start_timestamp,
        "evidence_root": str(evidence_root),
        "credential_status": credential_status(),
    }
    write_json(output_dir / "pre_change_manifest.json", pre_change)

    spec = build_frozen_spec(_latest_completed_trade_date())
    write_json(output_dir / "frozen_acquisition_spec.json", spec)

    records = inventory_sources(_default_roots())
    write_json(output_dir / "source_inventory.json", records)

    registry = recover_option_registry(records)
    registry_path = output_dir / "recovered_sensex_option_token_registry.parquet"
    try:
        registry.to_parquet(registry_path, index=False)
    except Exception:
        registry_path = output_dir / "recovered_sensex_option_token_registry.csv"
        registry.to_csv(registry_path, index=False)
    expiries = sorted([x for x in registry.get("expiry_date", pd.Series(dtype=str)).dropna().astype(str).unique().tolist() if x])
    duplicate_mappings = 0
    if not registry.empty:
        duplicate_mappings = int(registry.groupby(["tradingsymbol", "expiry_date"])["instrument_token"].nunique(dropna=True).gt(1).sum())
    registry_report = {
        "contracts_found": int(len(registry)),
        "expiries_covered": expiries,
        "earliest_expiry": expiries[0] if expiries else None,
        "latest_expiry": expiries[-1] if expiries else None,
        "weekly_versus_monthly_coverage": "UNRESOLVED_WITHOUT_COMPLETE_CONTRACT_METADATA" if expiries else "NONE",
        "missing_expiry_regimes": ["UNRESOLVED"],
        "duplicate_conflicting_token_mappings": duplicate_mappings,
        "successful_kite_lookups": 0,
        "failed_kite_lookups": 0,
        "failure_classes": {"invalid_token": 0, "unavailable_history": 0, "permission_failure": 0, "temporary_api_failure": 0, "not_attempted": int(len(registry))},
    }
    write_json(output_dir / "recovered_sensex_option_token_registry_report.json", registry_report)

    expiry_calendar = pd.DataFrame(columns=["trade_date", "expiry_date", "days_to_expiry", "expiry_type", "scheduled_weekday", "actual_expiry_weekday", "holiday_shifted", "expiry_regime", "evidence_source"])
    try:
        expiry_calendar.to_parquet(output_dir / "expiry_calendar.parquet", index=False)
    except Exception:
        expiry_calendar.to_csv(output_dir / "expiry_calendar.csv", index=False)

    five_minute_reconciliation = {
        "compared_sessions": 0,
        "compared_bars": 0,
        "exact_matches": 0,
        "ohlc_mismatches": 0,
        "volume_mismatches": 0,
        "missing_bars": 0,
        "timestamp_offset_mismatches": 0,
        "maximum_absolute_difference": None,
        "maximum_relative_difference": None,
        "likely_cause": "No newly acquired one-minute SENSEX source available in this run.",
    }
    write_json(output_dir / "five_minute_reconciliation_report.json", five_minute_reconciliation)

    audit = {
        "verdict": "FAIL",
        "reason": "Readiness-blocking data acquisition gaps remain; independent audit found no complete verified constituent panel or option OHLCV lane.",
        "source_count": len(records),
        "option_registry_rows": int(len(registry)),
        "five_minute_sample_recomputed": False,
        "constituent_coverage_recomputed": False,
        "option_token_mapping_unique": duplicate_mappings == 0,
    }
    write_json(output_dir / "independent_data_audit.json", audit)

    sensex_sources = [r for r in records if "sensex" in r["absolute_path"].lower()]
    payload = {
        "final_readiness_verdict": "INVALID_DATA_ACQUISITION",
        "kite_limitation_findings": [item.__dict__ for item in KITE_LIMITATION_FINDINGS],
        "inventory_summary": {
            "sources_indexed": len(records),
            "sensex_like_sources": len(sensex_sources),
            "instrument_registry_sources": sum(1 for r in records if r["type"] == "instrument_master_or_contract_registry"),
        },
        "sensex_underlying_coverage": "NOT_PROVEN_COMPLETE",
        "option_registry_report": registry_report,
        "expiry_regimes_covered": ["UNRESOLVED"],
        "blockers": [
            "Inventory was bounded to the active clean worktree and known immutable evidence subtrees; exhaustive traversal of every prior worktree/evidence file was too large for this interactive run.",
            "No complete historically valid SENSEX constituent membership and weight table was proven.",
            "SENSEX option token recovery did not verify any Kite historical lookups in this run.",
            "No complete one-minute raw/canonical acquisition was certified by the independent audit.",
            "Historical bid/ask is unavailable, so executable option certification remains impossible from OHLCV alone.",
        ],
    }
    write_json(output_dir / "data_readiness_report.json", payload)
    (output_dir / "data_readiness_report.md").write_text(build_readiness_report(payload), encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "evidence_root": str(evidence_root), "verdict": payload["final_readiness_verdict"], "sources": len(records), "option_registry_rows": int(len(registry))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
