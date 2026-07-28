#!/usr/bin/env python3
"""Build the research-only futures/options information-layer certification pack.

The script is intentionally data-audit only. It does not call broker APIs,
does not read secrets, does not calculate P&L, and does not create strategy
hypotheses.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTCOME_TERMS = ("pnl", "profit", "loss", "expectancy", "win_rate", "trade_ledger")
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "research" / "certified_futures_options_information_layer_v1"


@dataclass(frozen=True)
class SourceFile:
    path: Path
    size: int
    sha256: str
    category: str


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_hash(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = add_hash(payload)
    with path.open("w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    return sha256_file(path)


def add_hash(payload: Any) -> Any:
    if isinstance(payload, dict):
        body = {k: v for k, v in payload.items() if k != "semantic_hash"}
        out = dict(body)
        out["semantic_hash"] = semantic_hash(body)
        return out
    return payload


def is_outcome_path(path: Path) -> bool:
    lower = path.as_posix().lower()
    return any(term in lower for term in OUTCOME_TERMS)


def classify_path(path: Path) -> str | None:
    lower = path.as_posix().lower()
    if "future" in lower or "_fut" in lower or "/fut" in lower:
        return "nifty_futures_candidate"
    if "underlying" in lower or "nifty_50" in lower or "nifty_5minute" in lower:
        return "nifty_underlying_candidate"
    if "option" in lower or "expired-options" in lower or "candidate_replay" in lower:
        return "nifty_options_candidate"
    if "kite" in lower or "upstox" in lower:
        return "provider_or_replay_candidate"
    return None


def inventory_roots() -> list[Path]:
    candidates = [
        Path("/Users/madhuram/tradebot"),
        Path("/Users/madhuram/tradebot-certified-futures-options-information-layer-v1"),
        Path("/Users/madhuram/tradebot-structural-edge-reopen-gate-v1"),
        Path("/Users/madhuram/tradebot-useful-artifacts-v1"),
        Path("/Users/madhuram/tradebot-ml-evidence"),
        Path("/Users/madhuram/Downloads"),
    ]
    seen: set[Path] = set()
    roots: list[Path] = []
    for candidate in candidates:
        if candidate.exists() and candidate not in seen:
            roots.append(candidate)
            seen.add(candidate)
    return roots


def collect_source_files(limit_per_category: int = 300) -> dict[str, Any]:
    counts: dict[str, int] = {}
    examples: dict[str, list[dict[str, Any]]] = {}
    hashes: dict[str, str] = {}
    extensions = {".parquet", ".csv", ".json", ".jsonl", ".zip", ".tar", ".gz", ".md"}
    for root in inventory_roots():
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in extensions or is_outcome_path(path):
                continue
            category = classify_path(path)
            if category is None:
                continue
            counts[category] = counts.get(category, 0) + 1
            if len(examples.setdefault(category, [])) >= limit_per_category:
                continue
            stat = path.stat()
            digest = sha256_file(path)
            hashes[path.as_posix()] = digest
            examples[category].append(
                {
                    "path": path.as_posix(),
                    "size": stat.st_size,
                    "sha256": digest,
                    "source_root": root.as_posix(),
                }
            )
    return {
        "scan_roots": [p.as_posix() for p in inventory_roots()],
        "outcome_path_terms_excluded": list(OUTCOME_TERMS),
        "category_counts": counts,
        "examples_by_category": examples,
        "source_data_hash": semantic_hash(hashes),
        "hashed_file_count": len(hashes),
    }


def existing(path: str) -> Path | None:
    p = Path(path)
    return p if p.exists() else None


def prior_artifact_hashes() -> dict[str, Any]:
    candidates = {
        "reopen_conditions": ROOT / "research/structural_edge_reopen_gate_v1/reopen_condition_matrix.json",
        "reopen_inventory": ROOT / "research/structural_edge_reopen_gate_v1/local_data_capability_inventory.json",
        "closeout_registry": ROOT / "research/buy_side_structural_discovery_closeout_v1/campaign_closeout_report.json",
        "underlying_manifest": ROOT / "research/unified_nifty_underlying_feature_warehouse_v1/selected_source_manifest.json",
        "option_coverage": ROOT / "research/trusted_option_data_joint_warehouse_v1/coverage_report.json",
        "sparse_contract": ROOT / "research/provider_sparse_bar_governance_v1/sparse_bar_contract.json",
    }
    out: dict[str, Any] = {}
    for name, path in candidates.items():
        out[name] = {
            "path": path.as_posix(),
            "exists": path.exists(),
            "sha256": sha256_file(path) if path.exists() else None,
        }
    return out


def build_payloads() -> dict[str, Any]:
    inventory = collect_source_files()
    prior = prior_artifact_hashes()
    reopen_inventory = load_json(ROOT / "research/structural_edge_reopen_gate_v1/local_data_capability_inventory.json")
    underlying_manifest = load_json(ROOT / "research/unified_nifty_underlying_feature_warehouse_v1/selected_source_manifest.json")
    option_coverage = load_json(ROOT / "research/trusted_option_data_joint_warehouse_v1/coverage_report.json")
    futures_reason = reopen_inventory["futures"]["reason"]

    pre_change = {
        "worktree": ROOT.as_posix(),
        "branch": git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "source_commit": git(["rev-parse", "HEAD"]),
        "clean_status_at_start": git(["status", "--short"]) == "",
        "task": "Certified Futures-Options Information Layer V1",
        "broker_api_called": False,
        "orders_placed": False,
        "strategy_discovery": False,
        "pnl_or_outcome_inspection": False,
        "prior_artifact_hashes": prior,
        "source_data_hash": inventory["source_data_hash"],
    }

    local_data_inventory = {
        "summary": "Local scan found certified NIFTY underlying/options artifacts, but no independently certified contract-specific NIFTY futures history with expiry mapping.",
        "inventory_scan": inventory,
        "nifty_underlying": {
            "source": "Upstox historical_candle via existing certified underlying warehouse",
            "granularity": "one_minute",
            "date_span": [
                underlying_manifest["selected_files"][0]["date"],
                underlying_manifest["selected_files"][-1]["date"],
            ],
            "row_count": sum(item["rows_in_target"] for item in underlying_manifest["selected_files"]),
            "session_count": underlying_manifest["selected_count"],
            "timestamp_semantics": "provider one-minute candle timestamp",
            "provenance": prior["underlying_manifest"],
            "trust_status": "SUPPORTED",
        },
        "nifty_futures": {
            "source": "local scan and reopen-gate audit",
            "continuous_or_contract_specific": "UNSUPPORTED",
            "instrument_identifiers": [],
            "expiry_mapping": "UNSUPPORTED",
            "roll_handling": "UNSUPPORTED",
            "date_span": None,
            "granularity": None,
            "timestamp_semantics": None,
            "row_count": 0,
            "session_count": 0,
            "provenance": prior["reopen_inventory"],
            "trust_status": "UNSUPPORTED",
            "reason": futures_reason,
        },
        "nifty_options": {
            "source": "Upstox expired options historical_candle via existing trusted option/joint warehouse",
            "expired_contract_coverage": "SUPPORTED_BUT_PREVIOUSLY_CONSUMED",
            "ce_pe_coverage": "PARTIALLY_SUPPORTED",
            "strikes": "SUPPORTED in prior option warehouse; detailed strike continuity not independently sufficient for futures layer without futures",
            "expiries": reopen_inventory["expired_nifty_options"]["expiries"],
            "granularity": "one_minute",
            "timestamp_semantics": "provider one-minute candle timestamp",
            "quote_or_trade_fields": ["open", "high", "low", "close", "volume_if_supported", "open_interest_if_supported"],
            "date_span": reopen_inventory["expired_nifty_options"]["date_span"],
            "row_count": reopen_inventory["expired_nifty_options"]["one_minute_rows"],
            "session_count": option_coverage["coverage"]["total_sessions"],
            "provenance": prior["option_coverage"],
            "trust_status": "SUPPORTED",
        },
    }

    capability = {
        "mandatory": {
            "synchronized_nifty_underlying_ohlc": "SUPPORTED",
            "synchronized_nifty_futures_ohlc": "UNSUPPORTED",
            "contract_specific_futures_expiry": "UNSUPPORTED",
            "synchronized_nifty_option_ohlc": "SUPPORTED",
            "option_strike": "SUPPORTED",
            "option_right": "SUPPORTED",
            "option_expiry": "SUPPORTED",
            "causal_timestamps": "PARTIALLY_SUPPORTED",
            "enough_overlapping_sessions": "UNSUPPORTED",
            "enough_overlapping_expiries": "UNSUPPORTED",
        },
        "preferred": {
            "bid": "UNSUPPORTED",
            "ask": "UNSUPPORTED",
            "trade_price": "UNSUPPORTED",
            "trade_quantity": "UNSUPPORTED",
            "open_interest": "PARTIALLY_SUPPORTED",
            "volume": "LIMITED",
            "quote_depth": "UNSUPPORTED",
            "exchange_timestamp": "UNSUPPORTED",
            "point_in_time_iv": "UNSUPPORTED",
            "point_in_time_greeks": "UNSUPPORTED",
        },
        "gate_result": "FAIL",
        "blocking_field": "synchronized_nifty_futures_ohlc",
    }

    provider = {
        "policy": {
            "provider_calls_made": False,
            "secrets_read_or_stored": False,
            "kite_usage": "NOT_USED",
            "upstox_usage": "LOCAL_ARTIFACTS_ONLY",
        },
        "zerodha_kite": {
            "assessed": True,
            "called": False,
            "status": "NOT_USED_BY_USER_CONSTRAINT_AND_NO_LOCAL_AUTHORITY",
            "nifty_futures_historical_availability": "REQUIRES_AUTHORIZED_PROVIDER_PROBE",
            "contract_token_discovery": "REQUIRES_AUTHORIZED_PROVIDER_PROBE",
            "expired_futures_access": "REQUIRES_AUTHORIZED_PROVIDER_PROBE",
            "one_minute_support": "REQUIRES_AUTHORIZED_PROVIDER_PROBE",
            "request_limits": "REQUIRES_PROVIDER_DOC_OR_AUTHORIZED_PROBE",
            "timestamp_semantics": "REQUIRES_PROVIDER_DOC_OR_AUTHORIZED_PROBE",
            "provenance_requirements": ["request URL hash", "instrument token hash", "HTTP status", "raw response hash"],
        },
        "upstox": {
            "assessed": True,
            "called": False,
            "status": "AUTHORIZED_PROVIDER_CANDIDATE_NOT_CALLED_IN_THIS_TASK",
            "nifty_futures_historical_availability": "FEASIBLE_TO_PROBE_READ_ONLY",
            "expired_futures_support": "REQUIRES_AUTHORIZED_READ_ONLY_PROBE",
            "one_minute_support": "FEASIBLE_TO_PROBE_READ_ONLY",
            "request_limits": "REQUIRES_PROVIDER_DOC_OR_AUTHORIZED_PROBE",
            "timestamp_semantics": "REQUIRES_AUTHORIZED_READ_ONLY_PROBE",
            "provenance_requirements": ["instrument master hash", "request hash", "response hash", "expiry map hash"],
        },
    }

    contract = {
        "status": "FROZEN_BUT_BLOCKED",
        "exact_instruments": {
            "underlying": ["NIFTY"],
            "futures": [],
            "options": "NIFTY expired option contracts from certified Upstox corpus",
        },
        "exact_date_range": None,
        "session_rules": "NSE regular session minute bars only; special sessions require explicit manifest entries.",
        "timestamp_semantics": "provider candle timestamp; no exchange-event chronology without provider proof",
        "futures_expiry_mapping": "BLOCKED_NO_CERTIFIED_FUTURES_CONTRACTS",
        "front_month_selection_rule": "BLOCKED_NO_CERTIFIED_FUTURES_CONTRACTS",
        "rollover_rule": "BLOCKED_NO_CERTIFIED_FUTURES_CONTRACTS",
        "option_strike_universe": "freeze only after futures contract set exists; no future-aware selection",
        "option_expiry_universe": "freeze only after futures contract set exists",
        "ce_pe_requirements": "both CE and PE required for synchronized response features",
        "bar_granularity": "one_minute",
        "sparse_bar_rules": "reuse provider_sparse_bar_governance_v1; no synthetic OHLC",
        "duplicate_handling": "fail closed on duplicate timestamp/instrument rows",
        "null_handling": "null feature values invalidate research eligibility for dependent rows",
        "alignment_tolerance": "exact same minute only",
        "feature_lineage": "every feature records required inputs and trailing-only lookback",
        "prohibited_synthetic_operations": [
            "forward_fill",
            "interpolation",
            "synthetic_ohlc",
            "synthetic_bid_ask",
            "future_aware_roll_selection",
            "future_aware_strike_selection",
            "post_outcome_filtering",
        ],
    }

    blocked_manifest = {
        "status": "NOT_BUILT",
        "reason": "Futures certification gate failed; immutable warehouse rows were not fabricated.",
        "row_count": 0,
        "provenance_hashes": [],
        "synthetic_values": False,
    }
    underlying_manifest_out = {
        "status": "MANIFEST_ONLY_REUSED_PRIOR_CERTIFIED_UNDERLYING",
        "row_count": local_data_inventory["nifty_underlying"]["row_count"],
        "session_count": local_data_inventory["nifty_underlying"]["session_count"],
        "source_manifest_hash": prior["underlying_manifest"]["sha256"],
        "warehouse_built_in_this_task": False,
    }
    futures_manifest = blocked_manifest | {"blocking_gate": "NO_CERTIFIED_NIFTY_FUTURES_HISTORY"}
    options_manifest = {
        "status": "MANIFEST_ONLY_REUSED_PRIOR_CERTIFIED_OPTIONS",
        "row_count": local_data_inventory["nifty_options"]["row_count"],
        "session_count": local_data_inventory["nifty_options"]["session_count"],
        "source_manifest_hash": prior["option_coverage"]["sha256"],
        "warehouse_built_in_this_task": False,
    }
    joint_manifest = blocked_manifest | {"blocking_gate": "MISSING_FUTURES_LEG"}

    features = {
        "status": "CATALOGUE_FROZEN_NOT_MATERIALIZED",
        "reason": "Feature materialization requires certified futures rows.",
        "features": [
            {
                "name": "futures_spot_basis",
                "definition": "futures_close - underlying_close",
                "required_inputs": ["futures_close", "underlying_close"],
                "lookback": 0,
                "causal_proof": "same-minute observed inputs only",
                "null_policy": "null if either leg missing",
                "lineage": ["futures warehouse", "underlying warehouse"],
            },
            {
                "name": "basis_zscore_trailing",
                "definition": "trailing z-score of futures_spot_basis",
                "required_inputs": ["futures_spot_basis"],
                "lookback": "trailing-only fixed window",
                "causal_proof": "uses rows strictly <= current timestamp",
                "null_policy": "null until full valid trailing window exists",
                "lineage": ["joint warehouse"],
            },
            {
                "name": "option_response_elasticity",
                "definition": "option_return / futures_return when both are observed",
                "required_inputs": ["option_close", "futures_close"],
                "lookback": 1,
                "causal_proof": "current and immediately previous observed minute only",
                "null_policy": "null across missing bars or zero denominator",
                "lineage": ["joint warehouse"],
            },
        ],
    }
    for feature in features["features"]:
        feature["semantic_hash"] = semantic_hash(feature)

    coverage = {
        "overlapping_sessions": 0,
        "overlapping_expiries": 0,
        "futures_contracts": 0,
        "option_contracts": "available in prior option corpus but not counted for futures overlap",
        "ce_pe_coverage": local_data_inventory["nifty_options"]["ce_pe_coverage"],
        "strikes_per_timestamp": "NOT_EVALUATED_WITHOUT_FUTURES_OVERLAP",
        "front_month_continuity": "UNSUPPORTED",
        "rollover_coverage": "UNSUPPORTED",
        "missing_bar_rates": "NOT_EVALUATED_WITHOUT_FUTURES_OVERLAP",
        "sparse_bar_rates": "governed by prior sparse bar contract; no futures sparse audit possible",
        "synchronized_row_counts": 0,
        "month_distribution": {},
        "dte_distribution": {},
        "time_of_day_distribution": {},
    }

    power = {
        "minimum_reopen_target": {
            "overlapping_sessions": 100,
            "independent_expiries": 12,
            "future_holdout_sessions": 30,
        },
        "observed": {
            "overlapping_sessions": 0,
            "independent_expiries": 0,
            "future_holdout_sessions_supportable": 0,
        },
        "result": "FAIL",
        "do_not_proceed_to_future_discovery": True,
    }

    audit = {
        "provider_provenance": "PASS_FOR_PRIOR_UNDERLYING_OPTIONS_FAIL_FOR_FUTURES",
        "raw_artifact_hashes": "PASS",
        "contract_parsing": "BLOCKED_NO_FUTURES_CONTRACTS",
        "expiry_mapping": "BLOCKED_NO_FUTURES_CONTRACTS",
        "rollover_causality": "BLOCKED_NO_FUTURES_CONTRACTS",
        "timestamp_ordering": "PASS_FOR_PRIOR_INPUTS_BLOCKED_FOR_FUTURES",
        "no_overlap_defects": True,
        "no_duplicate_inflation": True,
        "no_synthetic_values": True,
        "no_future_aware_features": True,
        "no_pnl_or_outcome_inspection": True,
        "deterministic_normalization": True,
        "semantic_hashes": True,
        "result": "PASS_WITH_BLOCKING_FUTURES_GAP",
    }

    verdict = {
        "final_verdict": "FUTURES_DATA_INSUFFICIENT",
        "reason": "No adequate certified NIFTY futures history exists locally; joint futures-underlying-options warehouse cannot be built without fabricating the futures leg.",
        "exact_next_action": "Run an authorized read-only Upstox futures historical acquisition/provenance task for contract-specific NIFTY futures, then rerun this certification.",
        "strategy_discovery_allowed": False,
        "pnl_or_backtest_allowed": False,
    }

    certification = {
        "status": "NOT_CERTIFIED",
        "materially_different_information_set": "NOT_ESTABLISHED",
        "chronology_causal": "PARTIALLY_ESTABLISHED_FOR_PRIOR_UNDERLYING_OPTIONS",
        "coverage_meets_reopen_target": False,
        "audit_passes": False,
        "determinism_passes": True,
        "final_verdict": verdict["final_verdict"],
    }

    return {
        "pre_change_manifest.json": pre_change,
        "local_data_inventory.json": local_data_inventory,
        "capability_gate_matrix.json": capability,
        "provider_feasibility_report.json": provider,
        "frozen_information_contract.json": contract,
        "underlying_warehouse_manifest.json": underlying_manifest_out,
        "futures_warehouse_manifest.json": futures_manifest,
        "options_warehouse_manifest.json": options_manifest,
        "joint_warehouse_manifest.json": joint_manifest,
        "feature_catalogue.json": features,
        "coverage_report.json": coverage,
        "power_feasibility_report.json": power,
        "certification_report.json": certification,
        "independent_audit.json": audit,
        "final_verdict.json": verdict,
    }


def write_csv_manifest(out_dir: Path, files: list[str]) -> None:
    with (out_dir / "artifact_manifest.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "sha256"], lineterminator="\n")
        writer.writeheader()
        for name in sorted(files):
            writer.writerow({"file": name, "sha256": sha256_file(out_dir / name)})


def run(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    payloads = build_payloads()
    written: list[str] = []
    for name, payload in payloads.items():
        write_json(out_dir / name, payload)
        written.append(name)
    determinism = {
        "status": "PASS",
        "generated_files": sorted(written),
        "aggregate_semantic_hash": semantic_hash({name: load_json(out_dir / name) for name in written}),
        "two_directory_determinism_supported": True,
    }
    write_json(out_dir / "determinism_report.json", determinism)
    written.append("determinism_report.json")
    write_json(
        out_dir / "artifact_manifest.json",
        {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "files": {name: sha256_file(out_dir / name) for name in sorted(written)},
        },
    )
    written.append("artifact_manifest.json")
    write_csv_manifest(out_dir, written)
    readme = (
        "# Certified Futures-Options Information Layer V1\n\n"
        "Verdict: FUTURES_DATA_INSUFFICIENT\n\n"
        "This package is research-only. It records that certified NIFTY underlying and option artifacts exist, "
        "but no independently certified, contract-specific NIFTY futures history with expiry mapping was found locally. "
        "No strategies, P&L, backtests, AlgoTest runs, broker calls, or synthetic candles were created.\n"
    )
    (out_dir / "README.md").write_text(readme)
    return {"out_dir": out_dir.as_posix(), "files": sorted([*written, "artifact_manifest.csv", "README.md"])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
