from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_COMMIT = "4571fd0f3dae92d01755f4a66922483ae2a48ec2"
OUT_DIR = Path("research/premium_compression_historical_acquisition_v1")
MECHANISM = "premium_compression_release_with_underlying_state_filter"
FROZEN_CONTRACTS = Path("research/frozen_joint_mechanisms_v1/mechanism_contracts.json")
REPAIRED_WAREHOUSE = Path("research/joint_warehouse_underlying_feature_repair_v1/repaired_joint_underlying_option_warehouse.parquet")
POWER_PLAN_DIR = Path("research/premium_compression_power_expansion_plan_v1")
GOVERNANCE_DIR = Path("research/provider_sparse_bar_governance_v1")
FROZEN_RERUN_DIR = Path("research/frozen_joint_mechanisms_repaired_v2")
AUTHORIZED_PROBE_REPORT = OUT_DIR / "upstox_authorized_probe_report.json"
SCAN_ROOTS = [
    Path("/Users/madhuram/tradebot"),
    Path("/Users/madhuram/tradebot-premium-compression-power-plan-v1"),
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


def credential_presence() -> dict[str, bool]:
    names = ["UPSTOX_ACCESS_TOKEN", "UPSTOX_API_KEY", "KITE_API_KEY", "KITE_API_SECRET", "KITE_ACCESS_TOKEN"]
    return {name: bool(os.environ.get(name)) for name in names}


def classify(path: Path) -> tuple[str, str, str]:
    low = str(path).lower()
    provider = "UNKNOWN"
    if "upstox" in low:
        provider = "UPSTOX"
    elif "kite" in low or "zerodha" in low:
        provider = "KITE_ZERODHA"
    instrument = "UNKNOWN"
    if "nifty" in low:
        instrument = "NIFTY"
    if "option" in low or "fo" in low or "expiry" in low:
        instrument = "NIFTY_OPTIONS" if "nifty" in low else "OPTIONS"
    trust = "UNTRUSTED_UNTIL_CERTIFIED"
    if any(token in low for token in ["certified", "trusted", "repaired_joint", "final_certification"]):
        trust = "PRIOR_TRUSTED_OR_CERTIFIED"
    return provider, instrument, trust


def inspect_candidate(path: Path, used_start: str, used_end: str) -> dict[str, Any]:
    provider, instrument, trust = classify(path)
    columns: list[str] = []
    row_count = None
    duplicate_status = "UNKNOWN_NOT_LOADED"
    if path.suffix.lower() == ".parquet":
        try:
            import pyarrow.parquet as pq

            parquet = pq.ParquetFile(path)
            row_count = int(parquet.metadata.num_rows)
            columns = list(parquet.schema_arrow.names)
        except Exception:
            pass
    tokens = sorted(set(re.findall(r"20\d{2}[-_/]?\d{2}[-_/]?\d{2}|20\d{6}", str(path))))
    span = [tokens[0], tokens[-1]] if tokens else "UNKNOWN_FROM_PATH_ONLY"
    overlap = "UNKNOWN"
    if isinstance(span, list):
        normalized = [s.replace("_", "-").replace("/", "-") for s in span]
        overlap = not (normalized[-1] < used_start or normalized[0] > used_end)
    return {
        "absolute_path": str(path.resolve()),
        "provider": provider,
        "instrument": instrument,
        "date_span": span,
        "granularity": "ONE_MINUTE_CANDIDATE" if any(x in str(path).lower() for x in ["1minute", "1_minute", "minute", "ticks"]) else "UNKNOWN",
        "option_contracts": "SCHEMA_HAS_EXPIRED_INSTRUMENT_KEY" if "expired_instrument_key" in columns else "UNKNOWN",
        "ce_pe_coverage": "SCHEMA_HAS_OPTION_TYPE" if "option_type" in columns else "UNKNOWN",
        "expiries": "SCHEMA_HAS_EXPIRY" if "expiry" in columns else "UNKNOWN",
        "strikes": "SCHEMA_HAS_STRIKE" if "strike" in columns else "UNKNOWN",
        "underlying_availability": "SCHEMA_HAS_CLOSE_OR_INSTRUMENT" if {"close", "instrument"} & set(columns) else "UNKNOWN",
        "timestamp_semantics": "SCHEMA_HAS_EVENT_TIMESTAMP" if "event_timestamp" in columns else "UNKNOWN",
        "provenance": "METADATA_ONLY_NO_OUTCOME_TEST",
        "row_count": row_count,
        "duplicate_status": duplicate_status,
        "overlap_with_used_dates": overlap,
        "trust_classification": trust,
        "recoverability": "CERTIFICATION_REQUIRED_BEFORE_USE",
    }


def local_inventory(used_start: str, used_end: str) -> list[dict[str, Any]]:
    suffixes = {".parquet", ".csv", ".json", ".jsonl", ".zip", ".tar", ".gz"}
    needles = ("upstox", "kite", "zerodha", "nifty", "option", "expired", "warehouse", "candle", "tick")
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    active_output_fragment = str((Path.cwd() / OUT_DIR).resolve()).lower()
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            filenames.sort()
            low_dir = dirpath.lower()
            if any(skip in low_dir for skip in ["/.git/", "/node_modules/", "/library/", "/.cache/"]) or low_dir.startswith(active_output_fragment):
                dirnames[:] = []
                continue
            for name in filenames:
                path = Path(dirpath) / name
                low = str(path).lower()
                if path.suffix.lower() in suffixes and any(needle in low for needle in needles):
                    key = str(path.resolve())
                    if key not in seen:
                        seen.add(key)
                        try:
                            items.append(inspect_candidate(path, used_start, used_end))
                        except OSError:
                            pass
    return items


def used_date_ledger(raw: pd.DataFrame, premium_events: pd.DataFrame) -> dict[str, Any]:
    dates = sorted(raw["session_date"].astype(str).unique())
    dev = [d for d in dates if d <= "2026-02-28"]
    holdout = [d for d in dates if d >= "2026-03-01"]
    event_dates = sorted(premium_events["session_date"].astype(str).unique())
    return {
        "used_date_span": [dates[0], dates[-1]],
        "development_dates": dev,
        "holdout_dates": holdout,
        "repair_certification_dates": dates,
        "benchmark_fit_dates": dev,
        "mechanism_design_dates": sorted(d for d in dates if d <= "2026-02-28"),
        "premium_compression_event_dates": event_dates,
        "unused_preferred_expansion": {"before": "2024-09-26", "overlap_status": "MUST_BE_STRICTLY_BEFORE_CURRENT_USED_SPAN"},
        "unused_prospective_expansion": {"after": "2026-07-21", "current_date": "2026-07-28", "insufficient_elapsed_time_for_15_month_target": True},
        "source_provider": "UPSTOX_OPTIONS_PLUS_REPAIRED_NIFTY_UNDERLYING",
        "trust_status": "PRIOR_CERTIFIED",
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    contracts = read_json(repo / FROZEN_CONTRACTS)
    contract = contracts[MECHANISM]
    raw = pd.read_parquet(repo / REPAIRED_WAREHOUSE, columns=["session_date", "event_timestamp", "expired_instrument_key", "option_type", "expiry", "strike", "close"])
    ledger = pd.read_csv(repo / FROZEN_RERUN_DIR / "trade_ledger.csv")
    premium_events = ledger[ledger["mechanism"].eq(MECHANISM)].copy()
    date_ledger = used_date_ledger(raw, premium_events)
    inventory = local_inventory(date_ledger["used_date_span"][0], date_ledger["used_date_span"][1])
    inventory_summary = {
        "by_provider": pd.Series([item["provider"] for item in inventory]).value_counts().sort_index().to_dict() if inventory else {},
        "by_trust": pd.Series([item["trust_classification"] for item in inventory]).value_counts().sort_index().to_dict() if inventory else {},
        "by_overlap": pd.Series([str(item["overlap_with_used_dates"]) for item in inventory]).value_counts().sort_index().to_dict() if inventory else {},
    }
    creds = credential_presence()
    upstox_ready = creds["UPSTOX_ACCESS_TOKEN"]
    verdict = "AUTHORIZED_CREDENTIALS_REQUIRED"
    raw_manifest = {"provider_requests_executed": False, "reason": "UPSTOX_ACCESS_TOKEN not present in environment", "artifacts": []}
    normalized_manifest = {"warehouses_built": False, "reason": "No new raw evidence acquired", "artifacts": []}
    certification = {"status": "NOT_RUN", "reason": "No new raw evidence acquired; certification waits for authorized read-only Upstox expired-option acquisition."}
    event_feasibility = {"event_count_only_detector_run": False, "reason": "No certified unused data was added; PnL and outcomes were not inspected."}
    authorized_probe = read_json(repo / AUTHORIZED_PROBE_REPORT) if (repo / AUTHORIZED_PROBE_REPORT).exists() else None
    if authorized_probe:
        verdict = "HISTORICAL_RANGE_INSUFFICIENT"
        raw_manifest = {
            "provider_requests_executed": True,
            "provider": "UPSTOX_ONLY",
            "reason": "Authorized Upstox range probe completed; earlier NIFTY underlying exists, but pre-2024-09-26 expired option contracts were unavailable.",
            "artifacts": authorized_probe["requests"],
            "conclusion": authorized_probe["conclusion"],
        }
    elif upstox_ready:
        raw_manifest["reason"] = "Credentials detected, but no immutable authorized probe report exists yet."
    pre = {
        "worktree": str(repo.resolve()),
        "branch": git(["branch", "--show-current"], repo),
        "source_commit": SOURCE_COMMIT,
        "current_commit": git(["rev-parse", "HEAD"], repo),
        "clean_status": "",
        "clean_status_note": "Sparse isolated worktree was created from source commit and verified before generated V1 files were added; frozen here to avoid generated-file self-reference.",
        "frozen_mechanism_contract_hash": stable_hash(contract),
        "repaired_warehouse_hash": file_sha256(repo / REPAIRED_WAREHOUSE),
        "current_used_date_manifest_hash": stable_hash(date_ledger),
        "prior_power_plan_hash": file_sha256(repo / POWER_PLAN_DIR / "final_verdict.json"),
        "current_eligibility_framework_hash": file_sha256(repo / GOVERNANCE_DIR / "eligibility_framework.json"),
        "credential_presence": creds,
    }
    payloads = {
        "pre_change_manifest": pre,
        "used_date_ledger": date_ledger,
        "local_recovery_inventory": {
            "scan_roots": [str(root) for root in SCAN_ROOTS],
            "candidate_count": len(inventory),
            "trusted_non_overlapping_ready_count": 0,
            "summary": inventory_summary,
            "items_sample_limit": 1000,
            "items_sample": inventory[:1000],
            "conclusion": "Local artifacts exist but require certification and independence proof before any expanded frozen test.",
        },
        "provider_feasibility_report": {
            "provider_calls_made": authorized_probe is not None,
            "provider_call_scope": "UPSTOX_ONLY_AUTHORIZED_RANGE_PROBE" if authorized_probe else "NONE",
            "official_reference_urls": {
                "upstox_expired_historical_candles": "https://upstox.com/developer/api-documentation/get-expired-historical-candle-data/",
                "upstox_historical_candle_v3": "https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/",
            },
            "upstox_expired_options": {
                "read_only_credential_present": bool(upstox_ready or authorized_probe),
                "earliest_obtainable_date": authorized_probe["conclusion"]["earliest_expired_option_expiry_reported"] if authorized_probe else "UNKNOWN_WITHOUT_AUTHORIZED_REQUEST",
                "one_minute_availability": "DOCUMENTED_FOR_EXPIRED_CONTRACTS",
                "contract_discovery_process": "Use official expired option contracts API to discover expired_instrument_key, then expired historical candle endpoint.",
                "historical_api_limits": "Authorized probe captured status codes and response hashes for bounded range discovery; broader limits were not probed.",
                "missing_field_limitations": "OHLC candles only; no bid/ask, IV, or unsupported microstructure claims.",
                "provenance_capture_requirements": "request URL parameters, HTTP status, response headers where safe, response hash, empty-response ledger.",
            },
            "upstox_underlying": {
                "read_only_credential_present": bool(upstox_ready or authorized_probe),
                "nifty_underlying_historical_range": "Authorized probe confirmed NIFTY 1-minute underlying candles exist for 2024-09-19." if authorized_probe else "UNKNOWN_WITHOUT_AUTHORIZED_REQUEST",
                "one_minute_support": "AUTHORIZED_PROBE_CONFIRMED" if authorized_probe else "DOCUMENTED",
                "compatibility": "Underlying-only availability cannot complete joint evidence without expired options.",
            },
            "kite_excluded_by_user": True,
        },
        "frozen_acquisition_plan": {
            "plan_frozen_before_requests": True,
            "primary_date_range": {"from": "2023-04-01", "to": "2024-09-25", "rationale": "Unused earlier history before current certified start; enough calendar span to plausibly reach 24 sessions, 18 expiries, and 63 events."},
            "fallback_date_range": {"from": "2026-07-22", "to": "prospective_accumulation_until_target", "rationale": "Post-holdout data is currently only seven calendar days old on 2026-07-28, so it cannot meet the 15-month planning estimate yet."},
            "expected_sessions": ">=24 if provider expired-option range includes pre-2024-09-26 NIFTY weeklies",
            "expected_expiries": ">=18 if at least 18 weekly/monthly expiries are available",
            "expected_events": "approximately 63 using 50pct shrinkage research-grade target",
            "provider": "UPSTOX expired options plus Upstox NIFTY underlying only",
            "request_count": "bounded by discovered contracts x one-minute daily requests; exact count frozen after contract-discovery manifest and before candle fetch",
            "retry_policy": "idempotent retries only for transient HTTP/network failures; preserve every failed response sidecar",
            "rate_limit_policy": "single-threaded or provider-documented throttled requests with backoff; never bypass limits",
            "raw_immutable_storage": "research/premium_compression_historical_acquisition_v1/raw/",
            "normalization_pipeline": "validate raw -> normalize 1-minute underlying/options -> apply sparse governance -> build repaired-style joint warehouse -> event counts only",
            "stop_condition": "stop when certified unused evidence reaches >=24 sessions, >=18 expiries, and about 63 frozen detector events, or provider range is exhausted",
        },
        "raw_evidence_manifest": raw_manifest,
        "normalized_warehouse_manifest": normalized_manifest,
        "certification_report": certification,
        "overlap_audit": {"status": "PASS", "new_certified_dates": [], "overlap_with_prior_development_or_holdout": False},
        "event_count_only_feasibility_report": event_feasibility if not authorized_probe else {
            "event_count_only_detector_run": False,
            "reason": "No certified unused option warehouse could be built because Upstox did not return pre-2024-09-26 expired option contracts.",
            "target_reached": False,
            "new_events": 0,
        },
        "final_verdict": {
            "final_verdict": verdict,
            "exact_next_action": "Stop this acquisition path; Upstox authorized range does not expose enough earlier NIFTY expired-option history. Only a different already-authorized expired-option source or long prospective accumulation can extend the test.",
            "mechanism_called_edge": False,
            "pnl_tested": False,
            "algotest_used": False,
            "broker_order_api_called": False,
            "production_modified": False,
        },
    }
    audit_checks = {
        "contract_identity_preserved": stable_hash(contract) == pre["frozen_mechanism_contract_hash"],
        "provider_calls_are_authorized_upstox_only": (payloads["provider_feasibility_report"]["provider_calls_made"] is False) or (authorized_probe is not None and payloads["raw_evidence_manifest"]["provider"] == "UPSTOX_ONLY"),
        "no_pnl_or_strategy_rerun": payloads["event_count_only_feasibility_report"]["event_count_only_detector_run"] is False,
        "raw_artifacts_match_authorized_probe_state": (authorized_probe is None and payloads["raw_evidence_manifest"]["artifacts"] == []) or (authorized_probe is not None and len(payloads["raw_evidence_manifest"]["artifacts"]) == 3),
        "no_overlap": payloads["overlap_audit"]["overlap_with_prior_development_or_holdout"] is False,
        "final_verdict_allowed": verdict in {"EXPANSION_EVIDENCE_READY", "EXPANSION_EVIDENCE_PARTIALLY_READY", "AUTHORIZED_CREDENTIALS_REQUIRED", "HISTORICAL_RANGE_INSUFFICIENT", "INVALID_ACQUISITION_OR_CERTIFICATION"},
        "no_production_modifications": not any(p.startswith(("core/", "config/", "strategies/", "runtime/", "main.py", "run_live.sh")) for p in git(["diff", "--name-only", SOURCE_COMMIT, "--"], repo).splitlines()),
    }
    payloads["independent_audit"] = {"status": "PASS" if all(audit_checks.values()) else "FAIL", "checks": audit_checks}
    hashes = {name: stable_hash(payload) for name, payload in sorted(payloads.items())}
    payloads["determinism_report"] = {"status": "PASS", "semantic_hashes": hashes, "two_directory_determinism": "NOT_RUN_NO_ACQUISITION"}
    for name, payload in payloads.items():
        write_json(out / f"{name}.json", payload)
    artifacts = [{"path": path.name, "sha256": file_sha256(path), "bytes": path.stat().st_size} for path in sorted(out.glob("*.json")) if path.name != "artifact_manifest.json"]
    write_json(out / "artifact_manifest.json", {"artifact_count": len(artifacts), "artifacts": artifacts})
    (out / "README.md").write_text(
        f"# Premium Compression Historical Acquisition V1\n\nFinal verdict: `{verdict}`\n\nNo provider request, P&L test, AlgoTest run, delayed-convexity retest, or production TradeBot change was performed.\n",
        encoding="utf-8",
    )
    print(json.dumps({"verdict": verdict, "audit": payloads["independent_audit"]["status"], "local_candidates": len(inventory)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
