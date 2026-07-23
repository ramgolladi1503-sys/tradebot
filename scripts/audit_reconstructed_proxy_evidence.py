#!/usr/bin/env python3
"""Independent artifact oracle for reconstructed proxy research evidence.

This module intentionally imports no strategy or runner implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"unsupported table type: {path}")


def _check(checks: dict[str, bool], name: str, value: object) -> None:
    checks[name] = bool(value)


REQUIRED_ARTIFACT_STEMS = {
    "evaluation/signal_states_weighted", "evaluation/trade_outcomes_weighted",
    "evaluation/signal_states_unweighted", "evaluation/trade_outcomes_unweighted",
    "evaluation/matched_control", "evaluation/delayed_entry_outcomes",
    "reports/membership_coverage", "reports/membership_coverage_summary",
    "evaluation/summary", "evaluation/control_summary", "evaluation/delay_sensitivity",
    "evaluation/concentration", "evaluation/chronological_folds",
}

REQUIRED_FROZEN_FILES = {
    "accepted_raw_manifest", "rejected_raw_manifest", "ticker_resolution", "instrument_master",
    "proxy_source_manifest", "raw_weights", "normalized_weights", "normalized_bars",
    "session_grid", "session_policy", "weighted_strategy_source", "unweighted_strategy_source",
    "exact_bar_contract_source", "evidence_controls_source", "weighted_runner_source",
    "coverage_source", "oracle_source",
}


def _audit_v3(campaign_root: Path, output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: dict[str, bool] = {}
    errors: list[str] = []
    try:
        freeze_path = campaign_root / "pre_outcome_freeze.json"
        freeze = read_json(freeze_path)
        summary_path = campaign_root / "evaluation/summary.json"
        summary = read_json(summary_path)
        artifact_manifest_path = campaign_root / "manifests/artifact_manifest.json"
        artifact_manifest = read_json(artifact_manifest_path)

        _check(checks, "freeze_version", freeze.get("freeze_version") == "constituent_lead_lag_proxy_v3")
        _check(checks, "taxonomy_frozen", summary.get("proxy_final_decision") in freeze.get("final_taxonomy", []))
        frozen_file_map = dict(freeze.get("frozen_files") or {})
        _check(checks, "required_frozen_file_owners", REQUIRED_FROZEN_FILES.issubset(frozen_file_map))
        frozen_hashes: dict[str, str] = {}
        for name, item in frozen_file_map.items():
            path = Path(item.get("path", ""))
            actual = sha256(path) if path.is_file() else "MISSING"
            frozen_hashes[name] = actual
            _check(checks, f"frozen_file:{name}", actual == item.get("sha256"))
        _check(checks, "freeze_hash_matches_summary", sha256(freeze_path) == summary.get("pre_outcome_freeze_sha256"))

        artifact_stems = {str(Path(relative).with_suffix("")) for relative in artifact_manifest}
        _check(checks, "required_artifacts", REQUIRED_ARTIFACT_STEMS.issubset(artifact_stems))
        artifact_hashes: dict[str, str] = {}
        for relative, expected in dict(artifact_manifest).items():
            path = campaign_root / relative
            actual = sha256(path) if path.is_file() else "MISSING"
            artifact_hashes[relative] = actual
            _check(checks, f"artifact:{relative}", actual == expected)

        weighted_path = campaign_root / "evaluation/signal_states_weighted.parquet"
        if not weighted_path.exists():
            weighted_path = campaign_root / "evaluation/signal_states_weighted.csv"
        unweighted_path = campaign_root / "evaluation/signal_states_unweighted.parquet"
        if not unweighted_path.exists():
            unweighted_path = campaign_root / "evaluation/signal_states_unweighted.csv"
        coverage_path = campaign_root / "reports/membership_coverage.parquet"
        if not coverage_path.exists():
            coverage_path = campaign_root / "reports/membership_coverage.csv"
        session_grid_path = Path(freeze["frozen_files"]["session_grid"]["path"])
        states = read_table(weighted_path)
        unweighted = read_table(unweighted_path)
        coverage = read_table(coverage_path)
        session_grid = read_table(session_grid_path)

        reason_counts = {str(k): int(v) for k, v in states["reason"].astype(str).value_counts().to_dict().items()}
        unweighted_reason_counts = {str(k): int(v) for k, v in unweighted["reason"].astype(str).value_counts().to_dict().items()}
        weighted_signals = int(states["side"].isin(["LONG", "SHORT"]).sum())
        unweighted_signals = int(unweighted["side"].isin(["LONG", "SHORT"]).sum())
        completed_sessions = int(session_grid["session_classification"].eq("REGULAR_SESSION_COMPLETE").sum())
        decision_times = list(freeze.get("decision_times") or [])
        theoretical = completed_sessions * len(decision_times)

        _check(checks, "campaign_window", summary.get("campaign_window") == freeze.get("campaign_window"))
        _check(checks, "decision_times", summary.get("decision_times") == decision_times)
        _check(checks, "completed_sessions", int(summary.get("completed_regular_sessions", -1)) == completed_sessions)
        _check(checks, "theoretical_state_bound", int(summary.get("theoretical_max_state_rows", -1)) == theoretical)
        _check(checks, "weighted_state_rows", len(states) == theoretical == int(summary.get("state_rows", -1)))
        _check(checks, "unweighted_state_rows", len(unweighted) == theoretical == int(summary.get("unweighted_state_rows", -1)))
        _check(checks, "reason_count_sum", sum(reason_counts.values()) == len(states))
        _check(checks, "weighted_reason_summary", reason_counts == summary.get("state_reason_counts"))
        _check(checks, "unweighted_reason_summary", unweighted_reason_counts == summary.get("unweighted_state_reason_counts"))
        _check(checks, "weighted_signal_count", weighted_signals == int(summary.get("weighted_signals", -1)))
        _check(checks, "unweighted_signal_count", unweighted_signals == int(summary.get("unweighted_signals", -1)))

        state_keys = states[["session", "decision_time", "decision_timestamp"]].astype(str).sort_values(list(["session", "decision_time", "decision_timestamp"])).reset_index(drop=True)
        coverage_keys = coverage[["session", "decision_time", "decision_timestamp"]].astype(str).sort_values(list(["session", "decision_time", "decision_timestamp"])).reset_index(drop=True)
        _check(checks, "coverage_row_identity", state_keys.equals(coverage_keys))
        _check(checks, "coverage_row_count", len(coverage) == len(states))
        merged = states.merge(coverage, on=["session", "decision_time", "decision_timestamp"], suffixes=("_state", "_coverage"), how="outer", indicator=True)
        _check(checks, "coverage_join_complete", merged["_merge"].eq("both").all())
        _check(checks, "count_coverage_reconciles", ((merged["count_coverage_state"] - merged["count_coverage_coverage"]).abs() <= 1e-12).all())
        _check(checks, "weight_coverage_reconciles", ((merged["weight_coverage_state"] - merged["weight_coverage_coverage"]).abs() <= 1e-12).all())
        gate_rate = float((coverage["passes_count_coverage"].astype(bool) & coverage["passes_weight_coverage"].astype(bool)).mean()) if len(coverage) else 0.0
        _check(checks, "coverage_gate_pass_rate", abs(gate_rate - float(summary["coverage_summary"]["both_gates_pass_rate"])) <= 1e-12)

        control_summary = read_json(campaign_root / "evaluation/control_summary.json")
        delay_summary = read_json(campaign_root / "evaluation/delay_sensitivity.json")
        concentration = read_json(campaign_root / "evaluation/concentration.json")
        _check(checks, "control_summary_reconciles", control_summary == summary.get("control_result"))
        _check(checks, "delay_summary_reconciles", delay_summary == summary.get("delay_sensitivity"))
        _check(checks, "concentration_reconciles", concentration == summary.get("concentration"))

        decision = summary.get("proxy_final_decision")
        if decision == "NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT":
            _check(checks, "zero_verdict_weighted_zero", weighted_signals == 0)
            _check(checks, "zero_verdict_min_sessions", completed_sessions >= 120)
            _check(checks, "zero_verdict_post_warmup", int(summary.get("post_warmup_sessions", 0)) >= 100)
            _check(checks, "zero_verdict_coverage", gate_rate >= 0.95)
            _check(checks, "zero_verdict_unweighted_reported", len(unweighted) == theoretical)
            _check(checks, "zero_verdict_control_na", control_summary.get("result") == "NOT_APPLICABLE_ZERO_SIGNALS")
            _check(checks, "zero_verdict_delay_na", delay_summary.get("result") == "NOT_APPLICABLE_ZERO_SIGNALS")
            _check(checks, "zero_verdict_concentration_na", concentration.get("result") == "NOT_APPLICABLE_ZERO_SIGNALS")
        else:
            _check(checks, "nonzero_or_failure_taxonomy", decision in freeze.get("final_taxonomy", []))

        verdict = "PASS" if checks and all(checks.values()) else "FAIL"
        report = {
            "verdict": verdict,
            "checks": checks,
            "errors": errors,
            "freeze_sha256": sha256(freeze_path),
            "frozen_hashes": frozen_hashes,
            "artifact_hashes": artifact_hashes,
            "state_rows": int(len(states)),
            "unweighted_state_rows": int(len(unweighted)),
            "weighted_signals": weighted_signals,
            "unweighted_signals": unweighted_signals,
            "reason_counts": reason_counts,
            "coverage_gate_pass_rate": gate_rate,
            "proxy_final_decision": decision,
            "oracle_imports_strategy": False,
            "research_only": True,
            "allowed_for_live_execution": False,
        }
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        report = {
            "verdict": "FAIL",
            "checks": checks,
            "errors": errors,
            "oracle_imports_strategy": False,
            "research_only": True,
            "allowed_for_live_execution": False,
        }
    (output_dir / "oracle_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report



def _audit_legacy(
    evaluation_dir: Path,
    bars: Path,
    output_dir: Path,
    coverage_dir: Path | None = None,
) -> dict[str, object]:
    """Diagnose old bundles, which are never sufficient for v3 certification."""
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: dict[str, bool] = {}
    errors: list[str] = []
    try:
        bars_df = read_table(bars)
        state_path = evaluation_dir / "signal_states_weighted.parquet"
        if not state_path.exists():
            state_path = evaluation_dir / "signal_states_weighted.csv"
        states = read_table(state_path)
        sessions = int(bars_df["session"].astype(str).nunique()) if "session" in bars_df else 0
        state_rows = int(len(states))
        reason_counts = (
            {str(k): int(v) for k, v in states["reason"].astype(str).value_counts().to_dict().items()}
            if "reason" in states
            else {}
        )
        _check(checks, "state_count_bound", state_rows <= sessions * 10)
        _check(checks, "reason_count_sum", sum(reason_counts.values()) == state_rows)
        _check(checks, "pre_outcome_freeze_present", (evaluation_dir / "pre_outcome_freeze.json").is_file())
        _check(checks, "artifact_manifest_present", (evaluation_dir / "artifact_manifest.json").is_file())
        _check(checks, "summary_present", (evaluation_dir / "summary.json").is_file())
        _check(
            checks,
            "coverage_present",
            coverage_dir is not None
            and (coverage_dir / "membership_coverage_summary.json").is_file(),
        )
        report = {
            "verdict": "FAIL",
            "certification_status": "LEGACY_BUNDLE_NOT_CERTIFIABLE",
            "checks": checks,
            "errors": errors,
            "bars_sha256": sha256(bars),
            "sessions": sessions,
            "state_rows": state_rows,
            "reason_counts": reason_counts,
            "oracle_imports_strategy": False,
            "research_only": True,
            "allowed_for_live_execution": False,
        }
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        report = {
            "verdict": "FAIL",
            "certification_status": "LEGACY_BUNDLE_NOT_CERTIFIABLE",
            "checks": checks,
            "errors": errors,
            "oracle_imports_strategy": False,
            "research_only": True,
            "allowed_for_live_execution": False,
        }
    (output_dir / "oracle_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


def audit(*args: object, **kwargs: object) -> dict[str, object]:
    """Audit v3 campaigns, with fail-closed support for the old call shape."""
    if len(args) == 2 and not kwargs:
        return _audit_v3(Path(args[0]), Path(args[1]))
    if len(args) in {3, 4} and not kwargs:
        coverage_dir = Path(args[3]) if len(args) == 4 and args[3] is not None else None
        return _audit_legacy(Path(args[0]), Path(args[1]), Path(args[2]), coverage_dir)
    if {"campaign_root", "output_dir"}.issubset(kwargs):
        return _audit_v3(Path(kwargs["campaign_root"]), Path(kwargs["output_dir"]))
    raise TypeError(
        "audit expects (campaign_root, output_dir) or legacy "
        "(evaluation_dir, bars, output_dir[, coverage_dir])"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.campaign_root, args.output_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
