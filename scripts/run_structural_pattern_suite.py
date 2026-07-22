#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.structural_pattern_suite.contracts import (
    FEATURE_CONTRACT_HASH,
    RESEARCH_ONLY_FLAGS,
    THRESHOLD_FREEZE,
    StrategyId,
    canonical_hash,
)
from research.structural_pattern_suite.controls import empty_negative_control_report
from research.structural_pattern_suite.io import write_json_with_sidecar
from research.structural_pattern_suite.option_replay import unavailable_option_replay_report
from research.structural_pattern_suite.verdict import insufficient_data_strategy_verdict, suite_verdict
from research.structural_pattern_suite.wfa import chronological_folds


EXPECTED_KITE_HASH = "f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d"
DEFAULT_EVIDENCE_DIR = Path("/Users/madhuram/tradebot-ml-evidence/structural-pattern-suite-v1")
DEFAULT_KITE_ARCHIVE = Path("/Users/madhuram/tradebot/runtime/kite_candidate_replay.zip")
BASE_SHA = "a8fa0cf2"
BASE_REASON = (
    "Selected origin/research/kite-five-minute-governed-discovery-v1 because it is the latest local trustworthy "
    "research-framework base on top of structural-edge-prove-or-kill-v1 and contains governed five-minute source "
    "inventory, deterministic run-pair evidence, timestamp semantics, independent oracle artifacts, and workflow fixes."
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_text_with_sidecar(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def parquet_placeholder(path: Path) -> None:
    try:
        import pandas as pd

        pd.DataFrame(
            columns=[
                "strategy_id",
                "strategy_version",
                "symbol",
                "side",
                "session",
                "decision_timestamp",
                "entry_timestamp",
                "source_manifest_hash",
                "feature_contract_hash",
                "candidate_bundle_hash",
                "execution_eligibility",
                "research_only",
            ]
        ).to_parquet(path, index=False)
        digest = file_sha256(path)
        path.with_name(path.name + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    except Exception as exc:
        fallback = path.with_suffix(".json")
        write_json_with_sidecar(fallback, {"status": "PARQUET_UNAVAILABLE", "reason": str(exc), "rows": []})


def build_reports(output_dir: Path, kite_archive: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_hash = file_sha256(kite_archive) if kite_archive.is_file() else None
    kite_ok = archive_hash == EXPECTED_KITE_HASH
    source_authority = {
        "schema_version": "1.0",
        "selected_base_sha": BASE_SHA,
        "selected_base_reason": BASE_REASON,
        "aeron7_required": True,
        "aeron7_status": "NOT_FOUND_IN_LOCAL_INPUTS",
        "kite_archive": str(kite_archive),
        "kite_expected_sha256": EXPECTED_KITE_HASH,
        "kite_observed_sha256": archive_hash,
        "kite_hash_verified": kite_ok,
        "mock_option_files_excluded": True,
        "volume_zero_underlying_archive": True,
        "real_vwap_calculated": False,
        **RESEARCH_ONLY_FLAGS,
    }
    source_manifest_hash = canonical_hash(source_authority)
    strategy_contracts = {
        "schema_version": "1.0",
        "feature_contract_hash": FEATURE_CONTRACT_HASH,
        "contracts": THRESHOLD_FREEZE["strategies"],
        "router": {
            "priority": ["GAP_GO_LEADER_V1", "PRIOR_RANGE_LEADER_V1", "LATE_DAY_PERSISTENCE_V1"],
            "contradictory_sides": "NO_SIGNAL",
            "one_trade_per_symbol_day_default": True,
            "no_late_day_recovery_after_losing_morning_trade": True,
        },
        **RESEARCH_ONLY_FLAGS,
    }
    strategy_verdicts = [insufficient_data_strategy_verdict(strategy_id) for strategy_id in StrategyId]
    final_verdict = {
        "schema_version": "1.0",
        "suite_verdict": suite_verdict(strategy_verdicts),
        "strategies": strategy_verdicts,
        "certification_note": "No certification is emitted until exact-mask reconstruction, WFA, controls, real option replay, deterministic rerun, and oracle gates pass.",
        **RESEARCH_ONLY_FLAGS,
    }
    reports: dict[str, Any] = {
        "source_authority.json": source_authority,
        "strategy_contracts.json": strategy_contracts,
        "threshold_freeze.json": THRESHOLD_FREEZE,
        "candidate_bundle_hash.json": {"candidate_count": 0, "candidate_bundle_hash": canonical_hash([])},
        "chronological_folds.json": {"folds": chronological_folds([]), "status": "INSUFFICIENT_DATA"},
        "underlying_wfa.json": {"status": "INSUFFICIENT_DATA", "minimum_gate": "4_of_5_positive_net_median_folds"},
        "horizon_comparison.json": {"status": "INSUFFICIENT_DATA", "horizons": ["15m", "30m", "60m", "close"]},
        "matched_controls.json": {"status": "INSUFFICIENT_DATA"},
        "negative_controls.json": empty_negative_control_report(),
        "parameter_neighbourhood.json": {"status": "INSUFFICIENT_DATA", "neighbourhoods": THRESHOLD_FREEZE["parameter_neighbourhoods"]},
        "delay_sensitivity.json": {"status": "INSUFFICIENT_DATA", "checks": ["one_bar_delay", "two_bar_delay"]},
        "concentration.json": {"status": "INSUFFICIENT_DATA", "checks": ["best_five_session_removal", "best_month_removal"]},
        "option_replay.json": unavailable_option_replay_report("real historical option quote corpus was not supplied to this runner"),
        "production_compatibility.json": {"status": "FAIL_PRODUCTION_COMPATIBILITY", "reason": "30-minute option replay not proven"},
        "router_comparison.json": {"status": "INSUFFICIENT_DATA", "modes": ["independent", "one_trade_per_day_router"]},
        "independent_oracle.json": {"status": "INSUFFICIENT_DATA", "primary_strategy_imported": False},
        "determinism.json": {"status": "NOT_RUN", "required_runs": 2, "semantic_equality_required": True},
        "final_verdict.json": final_verdict,
    }
    reports["source_authority.json"]["source_manifest_hash"] = source_manifest_hash
    for name, payload in reports.items():
        write_json_with_sidecar(output_dir / name, payload)
    parquet_placeholder(output_dir / "candidate_manifest.parquet")
    report = "\n".join(
        [
            "# Structural Pattern Strategy Suite v1 Final Report",
            "",
            f"Selected base SHA: `{BASE_SHA}`",
            "",
            BASE_REASON,
            "",
            f"Kite archive hash verified: `{kite_ok}`",
            "",
            "Final suite verdict: `CERTIFY_NONE`",
            "",
            "Reason: this implementation freezes the strategy contracts and emits the evidence contract, but local authoritative Aeron7 bars and real historical option quote data were not available to complete certification. The runner fails closed rather than treating missing data or mock options as evidence.",
            "",
            "No production registration, broker calls, live execution, risk-policy changes, or feed-gate changes were made.",
            "",
        ]
    )
    write_text_with_sidecar(output_dir / "FINAL_REPORT.md", report)
    return {"output_dir": str(output_dir), "kite_hash_verified": kite_ok, "final_verdict": "CERTIFY_NONE"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline structural pattern research suite.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--kite-archive", type=Path, default=DEFAULT_KITE_ARCHIVE)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result = build_reports(args.output_dir, args.kite_archive)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
