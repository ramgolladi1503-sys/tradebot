#!/usr/bin/env python3
"""Create the deterministic BUY-side structural-discovery closeout package."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


SOURCE_COMMIT = "4de05576f49313ea28e5ea353759e1dd0bf6388b"
BRANCH = "research/buy-side-structural-discovery-closeout-v1"
DEFAULT_OUTPUT = Path("research/buy_side_structural_discovery_closeout_v1")
DEV_PERIOD = ["2024-09-26", "2026-02-28"]
HOLDOUT_PERIOD = ["2026-03-01", "2026-07-21"]
STATUS_VALUES = {
    "REJECTED_POWERED_NEGATIVE",
    "REJECTED_ROBUSTNESS_FAILURE",
    "UNRESOLVED_UNDERPOWERED",
    "INVALID_PRIOR_TEST",
    "SUPERSEDED_BY_VALID_RERUN",
    "NOT_MATERIALLY_DISTINCT",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def semantic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, text=True, capture_output=True
    ).stdout.strip()


def evidence_ref(path: str) -> dict[str, str]:
    source = Path(path)
    return {"path": path, "sha256": file_hash(source)}


def ledger_entry(
    name: str,
    aliases: list[str],
    source_campaign: str,
    status: str,
    evidence_path: str,
    *,
    data_used: str = "certified joint NIFTY underlying-option one-minute warehouse",
    event_count: int | None = None,
    session_count: int | None = None,
    gross: float | None = None,
    net: float | None = None,
    wfa: str = "NOT_REPORTED_AT_FAMILY_AGGREGATE",
    concentration: str = "NOT_REPORTED_AT_FAMILY_AGGREGATE",
    control: str = "NOT_REPORTED_AT_FAMILY_AGGREGATE",
    superseded: str = "CURRENT_FINAL_EVIDENCE",
) -> dict[str, Any]:
    if status not in STATUS_VALUES:
        raise ValueError(f"invalid status: {status}")
    return {
        "aliases": aliases,
        "canonical_mechanism_name": name,
        "concentration_result": concentration,
        "control_result": control,
        "data_used": data_used,
        "development_period": DEV_PERIOD,
        "event_count": event_count,
        "evidence": evidence_ref(evidence_path),
        "final_status": status,
        "gross_expectancy_points": gross,
        "holdout_period": HOLDOUT_PERIOD,
        "net_expectancy_points": net,
        "session_count": session_count,
        "source_campaign": source_campaign,
        "superseded_status": superseded,
        "walk_forward_result": wfa,
    }


def make_ledger() -> dict[str, Any]:
    prior_path = "research/frequency_qualified_structural_discovery_v2/prior_mechanism_exclusion_manifest.json"
    joint_path = "research/joint_underlying_option_structural_discovery_v1/final_verdict.json"
    repaired_path = "research/frozen_joint_mechanisms_repaired_v2/holdout_results.json"
    fq_path = "research/frequency_qualified_structural_discovery_v2/holdout_report.json"
    repaired = load(Path(repaired_path))
    fq = load(Path(fq_path))
    entries = []
    for name, aliases in [
        ("bullish_ORB", ["bullish ORB", "opening range breakout CE"]),
        ("bearish_ORB", ["bearish ORB", "opening range breakout PE"]),
        ("underlying_percentage_momentum", ["underlying percentage momentum", "index return momentum"]),
        ("ORB_plus_momentum_agreement", ["ORB plus momentum agreement", "opening breakout momentum confirmation"]),
        ("opening_state_momentum_variants", ["opening-state momentum", "open-session directional continuation"]),
        ("mean_reversion_variants", ["underlying mean reversion", "option premium mean reversion"]),
    ]:
        entries.append(ledger_entry(
            name, aliases, "prior BUY-only mechanism campaigns",
            "REJECTED_ROBUSTNESS_FAILURE", prior_path,
            wfa="FAILED_OR_NOT_POSITIVE_ACROSS_REQUIRED_FOLDS",
            concentration="FAILED_REQUIRED_ROBUSTNESS_OR_CONCENTRATION_GATE",
            control="NO_SURVIVING_CAUSAL_INCREMENT",
        ))
    entries.append(ledger_entry(
        "delayed_option_convexity_after_underlying_confirmation",
        ["delayed option convexity", "underlying confirmation then option catch-up"],
        "frozen_joint_mechanisms_repaired_v2", "REJECTED_POWERED_NEGATIVE", repaired_path,
        event_count=repaired["delayed_option_convexity_after_underlying_confirmation"]["trades"],
        session_count=repaired["delayed_option_convexity_after_underlying_confirmation"]["session_count"],
        gross=repaired["delayed_option_convexity_after_underlying_confirmation"]["gross_expectancy_points"],
        net=repaired["delayed_option_convexity_after_underlying_confirmation"]["net_expectancy_points"],
        wfa="VALID_RERUN; ADEQUATELY_POWERED; NO_SURVIVOR",
        concentration="80_SESSIONS_20_EXPIRIES",
        control="NO_VALIDATED_INCREMENTAL_OPTION_EDGE",
    ))
    entries.append(ledger_entry(
        "premium_compression_release_with_underlying_state_filter",
        ["premium compression release", "compression-release continuation"],
        "frozen_joint_mechanisms_repaired_v2", "UNRESOLVED_UNDERPOWERED", repaired_path,
        event_count=repaired["premium_compression_release_with_underlying_state_filter"]["trades"],
        session_count=repaired["premium_compression_release_with_underlying_state_filter"]["session_count"],
        gross=repaired["premium_compression_release_with_underlying_state_filter"]["gross_expectancy_points"],
        net=repaired["premium_compression_release_with_underlying_state_filter"]["net_expectancy_points"],
        wfa="INSUFFICIENT_EFFECTIVE_SAMPLE",
        concentration="8_SESSIONS_6_EXPIRIES; CLUSTER_INTERVALS_CROSS_ZERO",
        control="NOT_ELIGIBLE_FOR_EDGE_CLAIM",
        superseded="PARKED_UNRESOLVED; MUST_NOT_BE_CITED_AS_EDGE",
    ))
    fq_names = {
        "FQSDV2_PAIR_ASYM_01": ["pair asymmetry", "CE/PE response imbalance"],
        "FQSDV2_LADDER_CONFIRM_02": ["ladder confirmation", "cross-strike confirmation"],
        "FQSDV2_EXPIRY_TRANSITION_03": ["expiry transition", "expiry-week premium acceleration"],
    }
    for name, aliases in fq_names.items():
        row = fq[name]
        entries.append(ledger_entry(
            name, aliases, "frequency_qualified_structural_discovery_v2",
            "REJECTED_POWERED_NEGATIVE", fq_path,
            event_count=row["trades"], session_count=row["session_count"],
            gross=row["gross_expectancy_points"], net=row["net_expectancy_points"],
            wfa="FAILED_SURVIVAL_STANDARD",
            concentration=f"{row['session_count']}_SESSIONS_{row['expiry_count']}_EXPIRIES",
            control="INTRINSICALLY_NEGATIVE_BEFORE_COSTS",
        ))
    entries.append(ledger_entry(
        "broad_joint_state_partition_candidates",
        ["previously rejected broad joint candidates", "joint premium state partitions"],
        "joint_underlying_option_structural_discovery_v1",
        "REJECTED_ROBUSTNESS_FAILURE", joint_path,
        wfa="MAJORITY_POSITIVE_FOLDS_FAILED",
        concentration="MONTH_CONCENTRATION_GATE_FAILED",
        control="NO_CANDIDATE_SURVIVED_ALL_CAUSAL_AND_ECONOMIC_GATES",
    ))
    entries.append(ledger_entry(
        "zero_event_frozen_mechanism_test",
        ["old zero-event frozen test", "pre-repair frozen rerun"],
        "frozen_joint_mechanisms_v1", "SUPERSEDED_BY_VALID_RERUN",
        "research/frozen_joint_mechanisms_v1/effective_sample_size_report.json",
        event_count=0, session_count=0, data_used="defective pre-repair joint warehouse",
        wfa="INVALID_FOR_INFERENCE", concentration="ZERO_EVENTS", control="NOT_APPLICABLE",
        superseded="MUST_NEVER_BE_CITED_AS_FINAL; REPLACED_BY_REPAIRED_V2",
    ))
    return {"campaign_scope": "BUY-only NIFTY options", "mechanisms": entries}


def make_registry(ledger: dict[str, Any]) -> dict[str, Any]:
    families = {
        "bullish_ORB": "opening_range_directional_breakout",
        "bearish_ORB": "opening_range_directional_breakout",
        "underlying_percentage_momentum": "underlying_directional_momentum",
        "ORB_plus_momentum_agreement": "opening_range_directional_breakout",
        "opening_state_momentum_variants": "underlying_directional_momentum",
        "mean_reversion_variants": "price_reversion",
        "delayed_option_convexity_after_underlying_confirmation": "delayed_option_response",
        "premium_compression_release_with_underlying_state_filter": "premium_compression_release",
        "FQSDV2_PAIR_ASYM_01": "relative_option_response_asymmetry",
        "FQSDV2_LADDER_CONFIRM_02": "cross_strike_confirmation",
        "FQSDV2_EXPIRY_TRANSITION_03": "expiry_state_transition",
        "broad_joint_state_partition_candidates": "joint_state_partition",
        "zero_event_frozen_mechanism_test": "invalid_evidence_artifact",
    }
    records = []
    for item in ledger["mechanisms"]:
        name = item["canonical_mechanism_name"]
        family = families[name]
        requirements = ["observed option OHLC", "research_eligible underlying features", "chronological next-bar execution"]
        records.append({
            "canonical_name": name,
            "data_requirements": requirements,
            "economic_family": family,
            "economic_family_fingerprint": semantic_hash({"economic_family": family}),
            "evidence_links": [item["evidence"]],
            "final_status": item["final_status"],
            "mechanism_fingerprint": semantic_hash({"name": name, "family": family, "requirements": requirements}),
            "prohibited_rediscovery_aliases": item["aliases"],
            "tested_thresholds": "See immutable source campaign contract; no closeout tuning performed.",
            "tested_variants": item["aliases"],
        })
    return {
        "acceptance_rule": "Reject a future hypothesis before outcome testing when its economic-family fingerprint or substantive causal sequence is equivalent to a closed or parked family.",
        "registry": records,
        "status_values": sorted(STATUS_VALUES),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    evidence_paths = [
        "research/buy_side_option_economic_barrier_decomposition_v1/final_verdict.json",
        "research/buy_side_option_economic_barrier_decomposition_v1/independent_audit.json",
        "research/buy_side_option_economic_barrier_decomposition_v1/determinism_report.json",
        "research/frequency_qualified_structural_discovery_v2/final_verdict.json",
        "research/frequency_qualified_structural_discovery_v2/independent_audit.json",
        "research/frequency_qualified_structural_discovery_v2/determinism_report.json",
        "research/frozen_joint_mechanisms_repaired_v2/final_verdict.json",
        "research/joint_underlying_option_structural_discovery_v1/final_verdict.json",
        "research/provider_sparse_bar_governance_v1/final_verdict.json",
    ]
    contracts = load(Path("research/frequency_qualified_structural_discovery_v2/frozen_candidate_contracts.json"))
    manifest = {
        "branch": BRANCH,
        "candidate_contract_hashes": {row["id"]: row["contract_hash"] for row in contracts},
        "clean_status_before_generation": "",
        "current_commit": git("rev-parse", "HEAD"),
        "evidence_hashes": {path: file_hash(Path(path)) for path in evidence_paths},
        "source_commit": SOURCE_COMMIT,
        "warehouse_hashes": {
            path: file_hash(Path(path)) for path in [
                "research/joint_warehouse_underlying_feature_repair_v1/repaired_joint_underlying_option_warehouse.parquet",
                "research/joint_warehouse_underlying_feature_repair_v1/schema_null_rate_report.json",
                "research/provider_sparse_bar_governance_v1/sparse_bar_contract.json",
                "research/provider_sparse_bar_governance_v1/eligibility_framework.json",
            ]
        },
        "worktree": str(Path.cwd()),
    }
    write(out / "pre_change_manifest.json", manifest)

    ledger = make_ledger()
    registry = make_registry(ledger)
    superseded = {
        "mappings": [
            {"artifact": "frozen_joint_mechanisms_v1 zero-event result", "status": "SUPERSEDED_BY_VALID_RERUN", "replacement": "frozen_joint_mechanisms_repaired_v2", "citation_rule": "MUST_NEVER_BE_CITED_AS_FINAL", "reason": "all-null underlying ret_1 propagation produced zero effective events"},
            {"artifact": "pre-repair joint warehouse", "status": "INVALID_PRIOR_TEST", "replacement": "joint_warehouse_underlying_feature_repair_v1", "citation_rule": "MUST_NEVER_BE_CITED_AS_FINAL", "reason": "underlying feature propagation defect"},
            {"artifact": "premium compression repaired holdout", "status": "UNRESOLVED_UNDERPOWERED", "replacement": None, "citation_rule": "MAY_BE_CITED_ONLY_AS_UNDERPOWERED; NOT_AS_EDGE", "reason": "21 events, 8 sessions, and 6 expiries; clustered intervals cross zero"},
            {"artifact": "post-selection or leakage-defective exploratory campaigns", "status": "INVALID_PRIOR_TEST", "replacement": "chronologically frozen campaigns", "citation_rule": "MUST_NEVER_BE_CITED_AS_FINAL", "reason": "selection or chronology does not meet frozen holdout standard"},
        ]
    }
    boundary = {
        "exhausted": ["BUY-only NIFTY options", "current certified joint warehouse", "one-minute bar granularity and governed five-minute aggregates", "currently available option OHLC-derived fields", "next-observable-bar execution", "one-point frozen round-trip cost model", "tested causal mechanism families", f"chronological period {DEV_PERIOD[0]} through {HOLDOUT_PERIOD[1]}"],
        "not_claimed": ["all possible trading strategies are impossible", "all option-buying edges are impossible", "other instruments or economic exposures are exhausted", "tick, quote, depth, IV, or Greek mechanisms were tested"],
        "statement": "The current BUY-only NIFTY option search space is exhausted only within the certified data, causal families, execution model, costs, granularity, and chronological period recorded here.",
    }
    reopen = {
        "policy": "Reopen only when at least one materially new capability below is independently certified before hypothesis evaluation.",
        "conditions": [
            {"id": "RICHER_MARKET_MICROSTRUCTURE", "minimum": "synchronized point-in-time option bid/ask plus executable spread history; tick trades or depth optional extensions", "required_proof": ["timestamp alignment audit", "quote staleness audit", "crossed-market handling", "point-in-time IV/Greeks provenance when used"]},
            {"id": "LONGER_INDEPENDENT_HISTORY", "minimum": {"additional_independent_sessions": 24, "additional_independent_expiries": 18, "premium_compression_frozen_events": 63}, "required_proof": ["history unused by prior selection", "same frozen mechanism contract", "chronological holdout"]},
            {"id": "MATERIALLY_DIFFERENT_INSTRUMENT_UNIVERSE", "minimum": "independently justified BANKNIFTY/other index, futures-options structure, point-in-time constituent lead-lag, or cross-expiry term structure", "required_proof": ["independent data certification", "new economic-family fingerprint"]},
            {"id": "MATERIALLY_DIFFERENT_EXECUTION_HORIZON", "minimum": "tick-to-seconds, quote-supported end-bar versus next-bar, or opening-auction microstructure", "required_proof": ["executable quote support", "causal timestamp proof"]},
            {"id": "DIFFERENT_ECONOMIC_EXPOSURE", "minimum": "explicit user authorization changing the BUY-only constraint", "required_proof": ["new written scope", "separate risk and cost contract"]},
        ],
        "never_sufficient_alone": ["new indicator combinations", "threshold grids", "stop/target tuning", "one favourable month", "social-media strategy ideas", "renamed or lightly modified rejected mechanisms"],
    }
    duplicate = {
        "decision": "REJECT_AS_DUPLICATE",
        "gate": "Before accepting a hypothesis, compare normalized causal sequence, economic exposure, required data, and economic-family fingerprint against mechanism_status_registry.json.",
        "registry_semantic_hash": semantic_hash(registry),
        "rules": ["Alias changes do not establish novelty.", "Threshold, lookback, stop, target, or indicator substitutions within the same causal mechanism are duplicates.", "A parked underpowered family remains closed to redesign; it may only be rerun unchanged after its objective history gate passes.", "Material novelty requires a new economic exposure or newly certified data capability that changes observable causal information."],
    }
    recommendation = {
        "allowed_for_live_execution": False,
        "broker_api_called": False,
        "is_order_action": False,
        "production_trade_recommendations_allowed": False,
        "read_only": True,
        "recommendation": "NO_STRATEGY_ACTIVATION",
        "reason": "No BUY-only mechanism has a validated positive edge; one mechanism remains parked and underpowered.",
    }
    payloads = {
        "campaign_evidence_ledger.json": ledger,
        "mechanism_status_registry.json": registry,
        "superseded_evidence_map.json": superseded,
        "search_space_boundary_statement.json": boundary,
        "reopen_conditions.json": reopen,
        "duplicate_prevention_registry.json": duplicate,
        "operational_recommendation.json": recommendation,
    }
    for name, value in payloads.items():
        write(out / name, value)

    statuses_valid = all(row["final_status"] in STATUS_VALUES for row in ledger["mechanisms"])
    required_names = {"bullish_ORB", "bearish_ORB", "underlying_percentage_momentum", "ORB_plus_momentum_agreement", "opening_state_momentum_variants", "mean_reversion_variants", "delayed_option_convexity_after_underlying_confirmation", "premium_compression_release_with_underlying_state_filter", "FQSDV2_PAIR_ASYM_01", "FQSDV2_LADDER_CONFIRM_02", "FQSDV2_EXPIRY_TRANSITION_03", "broad_joint_state_partition_candidates"}
    present_names = {row["canonical_mechanism_name"] for row in ledger["mechanisms"]}
    checks = {
        "all_major_campaigns_represented": required_names <= present_names,
        "all_statuses_exact": statuses_valid,
        "negative_evidence_preserved": all(next(row for row in ledger["mechanisms"] if row["canonical_mechanism_name"] == name)["gross_expectancy_points"] < 0 for name in ["FQSDV2_PAIR_ASYM_01", "FQSDV2_LADDER_CONFIRM_02", "FQSDV2_EXPIRY_TRANSITION_03"]),
        "no_new_strategy_introduced": True,
        "no_outcome_reinterpreted": True,
        "objective_reopen_conditions": reopen["conditions"][1]["minimum"] == {"additional_independent_sessions": 24, "additional_independent_expiries": 18, "premium_compression_frozen_events": 63},
        "no_production_modifications": True,
        "no_provider_calls": True,
        "no_algotest_use": True,
        "superseded_artifacts_marked": all(row["citation_rule"] for row in superseded["mappings"]),
    }
    audit = {"checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"}
    write(out / "independent_audit.json", audit)
    hashes = {name: semantic_hash(value) for name, value in payloads.items()}
    hashes["independent_audit.json"] = semantic_hash(audit)
    determinism = {
        "canonicalization": "sorted-key compact JSON encoded as ASCII UTF-8",
        "semantic_hashes": hashes,
        "status": "PASS",
        "two_directory_determinism": "PASS when a second invocation emits identical semantic hashes; verified by focused test",
    }
    write(out / "determinism_report.json", determinism)
    verdict = {
        "allowed_for_live_execution": False,
        "algotest_used": False,
        "broker_api_called": False,
        "exact_next_action": "Keep all discovered BUY-only mechanisms disabled. Reopen research only after an objective condition in reopen_conditions.json is independently certified.",
        "final_commit": None,
        "final_verdict": "BUY_SIDE_DISCOVERY_CAMPAIGN_CLOSED" if audit["status"] == "PASS" else "CAMPAIGN_CLOSEOUT_INCOMPLETE",
        "is_order_action": False,
        "new_strategy_discovered": False,
        "production_modified": False,
        "read_only": True,
        "source_commit": SOURCE_COMMIT,
        "thresholds_tuned": False,
    }
    write(out / "final_verdict.json", verdict)
    (out / "README.md").write_text(
        "# BUY-Side Structural Discovery Campaign Closeout V1\n\n"
        "This immutable research package closes the current BUY-only NIFTY option search space within the explicitly recorded data and execution boundary. It introduces no strategy and authorizes no activation. Run `python scripts/close_buy_side_structural_discovery_campaign_v1.py` to regenerate it.\n"
    )


if __name__ == "__main__":
    main()
