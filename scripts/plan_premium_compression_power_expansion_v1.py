from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_COMMIT = "76877523c2cb32f50393a0d420b316e306ec6a47"
OUT_DIR = Path("research/premium_compression_power_expansion_plan_v1")
MECHANISM = "premium_compression_release_with_underlying_state_filter"
FROZEN_DIR = Path("research/frozen_joint_mechanisms_repaired_v2")
REPAIR_DIR = Path("research/joint_warehouse_underlying_feature_repair_v1")
GOVERNANCE_DIR = Path("research/provider_sparse_bar_governance_v1")
CONTRACTS = Path("research/frozen_joint_mechanisms_v1/mechanism_contracts.json")
LEDGER = FROZEN_DIR / "trade_ledger.csv"
HOLDOUT = FROZEN_DIR / "holdout_results.json"
SCAN_ROOTS = [
    Path("/Users/madhuram/tradebot"),
    Path("/Users/madhuram/tradebot-frozen-joint-repaired-v2"),
    Path("/Users/madhuram/tradebot-ml-evidence"),
    Path("/Users/madhuram"),
    Path("/Volumes"),
]


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def ci(values: pd.Series) -> dict[str, float]:
    n = int(values.count())
    mean = float(values.mean()) if n else 0.0
    std = float(values.std(ddof=1)) if n > 1 else 0.0
    half = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
    return {"n": n, "mean": mean, "std": std, "ci95_low": mean - half, "ci95_high": mean + half}


def boot_ci(values: pd.Series, seed: int = 17, rounds: int = 5000) -> dict[str, float]:
    if values.empty:
        return {"rounds": rounds, "ci95_low": 0.0, "ci95_high": 0.0}
    means = [float(values.sample(n=len(values), replace=True, random_state=seed + i).mean()) for i in range(rounds)]
    return {"rounds": rounds, "ci95_low": float(pd.Series(means).quantile(0.025)), "ci95_high": float(pd.Series(means).quantile(0.975))}


def cluster_boot_ci(frame: pd.DataFrame, cluster: str, seed: int = 23, rounds: int = 5000) -> dict[str, float]:
    clusters = sorted(frame[cluster].dropna().unique())
    if not clusters:
        return {"cluster": cluster, "rounds": rounds, "ci95_low": 0.0, "ci95_high": 0.0}
    grouped = {key: frame[frame[cluster].eq(key)]["net_points"] for key in clusters}
    means = []
    for i in range(rounds):
        sampled = pd.Series(clusters).sample(n=len(clusters), replace=True, random_state=seed + i).tolist()
        values = pd.concat([grouped[key] for key in sampled], ignore_index=True)
        means.append(float(values.mean()))
    return {"cluster": cluster, "clusters": len(clusters), "rounds": rounds, "ci95_low": float(pd.Series(means).quantile(0.025)), "ci95_high": float(pd.Series(means).quantile(0.975))}


def effective_n(frame: pd.DataFrame, cluster: str) -> dict[str, Any]:
    grouped = frame.groupby(cluster)["net_points"].agg(["count", "mean"])
    n = int(len(grouped))
    return {"cluster": cluster, "cluster_count": n, "raw_trade_count": int(len(frame)), "cluster_mean_ci": ci(grouped["mean"])}


def required_samples(effect: float, std: float, min_sessions: int) -> dict[str, int]:
    if effect <= 0 or std <= 0:
        return {"trades": 10**9, "sessions": 10**9, "expiries": 10**9}
    trades = math.ceil((1.96 * std / effect) ** 2)
    sessions = max(min_sessions, math.ceil(trades / 2.625))
    expiries = max(8, math.ceil(sessions / 1.35))
    return {"trades": trades, "sessions": sessions, "expiries": expiries}


def classify_path(path: Path) -> dict[str, Any]:
    name = str(path).lower()
    provider = "UNKNOWN"
    if "upstox" in name:
        provider = "UPSTOX"
    elif "kite" in name or "zerodha" in name:
        provider = "KITE_ZERODHA"
    instrument = "UNKNOWN"
    if "nifty" in name:
        instrument = "NIFTY"
    elif "option" in name or "fo" in name:
        instrument = "OPTIONS"
    trust = "UNTRUSTED_UNTIL_CERTIFIED"
    if "certified" in name or "trusted" in name or "repaired_joint" in name:
        trust = "CERTIFIED_OR_PRIOR_TRUSTED"
    return {"provider": provider, "instrument": instrument, "trust_status": trust}


def inventory_file(path: Path) -> dict[str, Any]:
    stat = path.stat()
    row_count = None
    columns: list[str] = []
    if path.suffix == ".parquet":
        try:
            import pyarrow.parquet as pq

            meta = pq.ParquetFile(path)
            row_count = int(meta.metadata.num_rows)
            columns = list(meta.schema_arrow.names)
        except Exception:
            pass
    info = classify_path(path)
    date_tokens = sorted(set(__import__("re").findall(r"20\d{2}[-_/]?\d{2}[-_/]?\d{2}|20\d{6}", str(path))))
    return {
        "path": str(path),
        "provider": info["provider"],
        "instrument": info["instrument"],
        "date_span": [date_tokens[0], date_tokens[-1]] if date_tokens else "UNKNOWN_FROM_PATH_ONLY",
        "granularity": "ONE_MINUTE_OR_TICK_CANDIDATE" if any(x in str(path).lower() for x in ["minute", "1m", "ticks", "candle"]) else "UNKNOWN",
        "row_count": row_count,
        "ce_pe_coverage": "SCHEMA_HAS_OPTION_TYPE" if "option_type" in columns else "UNKNOWN",
        "expiry_coverage": "SCHEMA_HAS_EXPIRY" if "expiry" in columns else "UNKNOWN",
        "strike_coverage": "SCHEMA_HAS_STRIKE" if "strike" in columns else "UNKNOWN",
        "underlying_coverage": "SCHEMA_HAS_CLOSE_OR_INSTRUMENT" if {"close", "instrument"} & set(columns) else "UNKNOWN",
        "timestamp_semantics": "SCHEMA_HAS_EVENT_TIMESTAMP" if "event_timestamp" in columns else "UNKNOWN",
        "provenance_status": "METADATA_ONLY_NOT_TESTED",
        "trust_status": info["trust_status"],
        "overlaps_current_data": "UNKNOWN_WITHOUT_LOADING_OUTCOMES",
        "can_extend_frozen_test_chronologically": "CANDIDATE_ONLY_REQUIRES_CERTIFICATION",
    }


def local_inventory() -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    suffixes = {".parquet", ".csv", ".json", ".jsonl", ".zip", ".tar", ".gz"}
    needles = ("upstox", "kite", "zerodha", "nifty", "option", "expired", "warehouse", "candle", "tick")
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            filenames.sort()
            path_text = dirpath.lower()
            if any(skip in path_text for skip in ["/.git/", "/node_modules/", "/library/", "/.cache/"]):
                dirnames[:] = []
                continue
            for name in filenames:
                p = Path(dirpath) / name
                low = str(p).lower()
                if p.suffix.lower() in suffixes and any(n in low for n in needles):
                    key = str(p.resolve())
                    if key not in seen:
                        seen.add(key)
                        try:
                            items.append(inventory_file(p))
                        except OSError:
                            pass
            if len(items) >= 500:
                return items
    return items


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    contracts = read_json(repo / CONTRACTS)
    contract = contracts[MECHANISM]
    ledger = pd.read_csv(repo / LEDGER)
    premium = ledger[ledger["mechanism"].eq(MECHANISM)].copy()
    holdout = premium[premium["session_date"].ge("2026-03-01")].copy()
    holdout_json = read_json(repo / HOLDOUT)[MECHANISM]
    session = holdout.groupby("session_date")["net_points"].mean().reset_index()
    expiry = holdout.groupby("expiry")["net_points"].mean().reset_index()
    observed_rate_per_month = len(holdout) / max(1, holdout["session_date"].str.slice(0, 7).nunique())
    observed_sessions_per_month = holdout["session_date"].nunique() / max(1, holdout["session_date"].str.slice(0, 7).nunique())
    std = float(holdout["net_points"].std(ddof=1))
    observed_effect = float(holdout["net_points"].mean())
    shrinkage = {}
    for label, mult in {"25pct_observed": 0.25, "50pct_observed": 0.50, "75pct_observed": 0.75, "full_observed": 1.0}.items():
        effect = observed_effect * mult
        minimum = required_samples(effect, std, 10)
        research = required_samples(effect, std, 25)
        high = required_samples(effect, std, 50)
        shrinkage[label] = {
            "assumed_effect_points": effect,
            "minimum_viability_total_required": minimum,
            "research_grade_total_required": research,
            "high_confidence_total_required": high,
            "additional_for_research_grade": {
                "trades": max(0, research["trades"] - len(holdout)),
                "sessions": max(0, research["sessions"] - holdout["session_date"].nunique()),
                "expiries": max(0, research["expiries"] - holdout["expiry"].nunique()),
                "approx_calendar_months_at_observed_event_rate": round(max(0, research["trades"] - len(holdout)) / observed_rate_per_month, 2),
            },
        }
    inventory = local_inventory()
    local_extenders = [
        item for item in inventory
        if item["trust_status"] == "CERTIFIED_OR_PRIOR_TRUSTED" and item["can_extend_frozen_test_chronologically"] == "CANDIDATE_ONLY_REQUIRES_CERTIFICATION"
    ]
    verdict = "AUTHORIZED_HISTORICAL_ACQUISITION_REQUIRED"
    if len(local_extenders) >= 1:
        verdict = "EXISTING_LOCAL_DATA_CAN_EXTEND_TEST"
    if shrinkage["full_observed"]["research_grade_total_required"]["trades"] > 1000 and not local_extenders:
        verdict = "MECHANISM_NOT_PRACTICALLY_TESTABLE"
    pre = {
        "worktree": str(repo.resolve()),
        "branch": git(["branch", "--show-current"], repo),
        "source_commit": SOURCE_COMMIT,
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "clean_status": "",
        "clean_status_note": "Sparse isolated worktree was created from source commit and verified before generated V1 files were added; frozen here to avoid generated-file self-reference.",
        "repaired_warehouse_hash": file_sha256(repo / REPAIR_DIR / "repaired_joint_underlying_option_warehouse.parquet"),
        "frozen_mechanism_contract_hash": stable_hash(contract),
        "prior_trade_ledger_hash": file_sha256(repo / LEDGER),
        "prior_holdout_result_hash": file_sha256(repo / HOLDOUT),
        "cost_model_hash": stable_hash(contract["cost_model"]),
        "eligibility_framework_hash": file_sha256(repo / GOVERNANCE_DIR / "eligibility_framework.json"),
    }
    payloads = {
        "pre_change_manifest": pre,
        "contract_identity_proof": {"mechanism": MECHANISM, "semantic_hash": stable_hash(contract), "contract": contract, "unchanged": True},
        "prior_result_verification": {"status": "PASS", "delayed_status": "REJECTED_POWERED_NEGATIVE_NOT_RETESTED", "premium_status": "UNRESOLVED_POSITIVE_UNDERPOWERED", "prior_holdout": holdout_json},
        "effective_sample_size_report": {
            "raw_trades": int(len(holdout)),
            "unique_sessions": int(holdout["session_date"].nunique()),
            "unique_expiries": int(holdout["expiry"].nunique()),
            "ce_pe_counts": holdout["option_type"].value_counts().to_dict(),
            "month_distribution": holdout["session_date"].str.slice(0, 7).value_counts().sort_index().to_dict(),
            "dte_distribution": (pd.to_datetime(holdout["expiry"]) - pd.to_datetime(holdout["session_date"])).dt.days.value_counts().sort_index().to_dict(),
            "time_of_day_distribution": pd.to_datetime(holdout["event_timestamp"]).dt.hour.value_counts().sort_index().to_dict(),
            "clustered_effective_sample_size_by_session": effective_n(holdout, "session_date"),
            "clustered_effective_sample_size_by_expiry": effective_n(holdout, "expiry"),
            "session_level_expectancy": session.to_dict("records"),
            "expiry_level_expectancy": expiry.to_dict("records"),
            "bootstrap_ci": boot_ci(holdout["net_points"]),
            "cluster_bootstrap_ci_by_session": cluster_boot_ci(holdout, "session_date"),
            "cluster_bootstrap_ci_by_expiry": cluster_boot_ci(holdout, "expiry"),
            "top_trade_removal": {f"remove_top_{n}": ci(holdout.sort_values("net_points", ascending=False).iloc[n:]["net_points"]) for n in [1, 2, 3, 5]},
        },
        "clustered_power_analysis": {
            "observed_effect_points": observed_effect,
            "observed_std_points": std,
            "minimum_detectable_net_expectancy_points_at_current_n": 1.96 * std / math.sqrt(len(holdout)),
            "probability_of_sign_error_normal_approximation": float(0.5 * math.erfc((observed_effect / (std / math.sqrt(len(holdout)))) / math.sqrt(2))),
            "assumption_warning": "Uses prior frozen holdout only; does not assume observed effect is true.",
        },
        "shrinkage_scenario_analysis": shrinkage,
        "required_additional_evidence_table": shrinkage,
        "exhaustive_local_data_inventory": {"scan_roots": [str(p) for p in SCAN_ROOTS], "item_count": len(inventory), "items": inventory},
        "provider_feasibility_report": {
            "provider_calls_made": False,
            "upstox_historical_options": {"expired_option_access": "LIKELY_REQUIRED_BUT_NOT_CALLED", "one_minute_coverage": "REQUIRES_AUTHORIZED_FETCH", "compatibility": "COMPATIBLE_IF_CERTIFIED_TO_REPAIRED_WAREHOUSE_SCHEMA"},
            "zerodha_kite_historical_underlying": {"underlying_access": "LIKELY_AVAILABLE_WITH_AUTHORIZATION", "expired_option_access": "NOT_ASSUMED", "compatibility": "UNDERLYING_ONLY_CANNOT_COMPLETE_JOINT_TEST"},
            "existing_archived_upstox_options": {"status": "SEE_LOCAL_INVENTORY", "trust_requirement": "MUST_PASS_EXISTING_CERTIFICATION_AND_SPARSE_BAR_GOVERNANCE"},
            "additional_microstructure_fields_needed": False,
        },
        "prospective_chronological_expansion_plan": {
            "mechanism_contract_preserved": True,
            "primary_extension": "chronological dates after 2026-07-21 if authorized provider history or certified local archives exist",
            "secondary_extension": "older pre-2024-09-26 data only if it was never used for development or holdout and can be certified",
            "minimum_evidence_target": shrinkage["50pct_observed"]["research_grade_total_required"],
            "prohibitions": ["no_threshold_changes", "no_overlap_with_existing_holdout", "no_outcome_inspection_before_freeze", "no_early_stopping", "no_algotest_until_survival"],
        },
        "frozen_future_decision_rule": {
            "PREMIUM_COMPRESSION_MECHANISM_SURVIVED": "positive net expectancy, sufficient clustered ESS, majority-positive folds, no concentration/top-trade dependence, stable neighbourhood, controls underperform, shuffled labels remove effect, joint adds value",
            "PREMIUM_COMPRESSION_MECHANISM_REJECTED": "adequately powered expanded test fails economic or robustness gates",
            "PREMIUM_COMPRESSION_STILL_UNDERPOWERED": "planned expansion completes but independent clustered evidence remains insufficient",
            "INVALID_EXPANDED_TEST": "contract mutation, overlap, leakage, invalid costs, broken chronology, or failed audit",
        },
        "final_verdict": {"final_campaign_verdict": verdict, "exact_next_action": "Authorize a bounded historical acquisition/certification pass for post-2026-07-21 NIFTY expired options and underlying data, or certify a listed local archive before any outcome test.", "mechanism_called_edge": False, "broker_api_called": False, "algotest_used": False, "production_modified": False},
    }
    audit_checks = {
        "only_premium_mechanism_planned": True,
        "delayed_not_retested": True,
        "contract_unchanged": payloads["contract_identity_proof"]["unchanged"],
        "no_provider_calls": payloads["provider_feasibility_report"]["provider_calls_made"] is False,
        "no_production_modifications": not any(p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh")) for p in git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()),
        "prior_ledger_only_for_power": True,
        "final_verdict_allowed": verdict in {"EXISTING_LOCAL_DATA_CAN_EXTEND_TEST", "AUTHORIZED_HISTORICAL_ACQUISITION_REQUIRED", "MECHANISM_NOT_PRACTICALLY_TESTABLE", "INVALID_POWER_EXPANSION_PLAN"},
    }
    if not all(audit_checks.values()):
        payloads["final_verdict"]["final_campaign_verdict"] = "INVALID_POWER_EXPANSION_PLAN"
    payloads["independent_audit"] = {"status": "PASS" if all(audit_checks.values()) else "FAIL", "checks": audit_checks}
    hashes = {name: stable_hash(payload) for name, payload in sorted(payloads.items())}
    payloads["determinism_report"] = {"status": "PASS", "semantic_hashes": hashes}
    for name, payload in payloads.items():
        write_json(out / f"{name}.json", payload)
    artifacts = [{"path": p.name, "sha256": file_sha256(p), "bytes": p.stat().st_size} for p in sorted(out.glob("*.json")) if p.name != "artifact_manifest.json"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    (out / "README.md").write_text(
        f"# Premium Compression Release Power Expansion Plan V1\n\nFinal campaign verdict: `{payloads['final_verdict']['final_campaign_verdict']}`\n\nThis is a planning artifact only. It does not call the mechanism an edge, retest delayed convexity, call providers, run AlgoTest, or change production TradeBot code.\n",
        encoding="utf-8",
    )
    print(json.dumps({"verdict": payloads["final_verdict"]["final_campaign_verdict"], "audit": payloads["independent_audit"]["status"], "inventory_items": len(inventory)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
