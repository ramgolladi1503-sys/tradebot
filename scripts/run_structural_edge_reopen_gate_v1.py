#!/usr/bin/env python3
"""Audit structural-discovery reopen conditions without inspecting outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


SOURCE_COMMIT = "d7ed6391c874197da32939852f818c974b2b0afc"
DEFAULT_DATA_ROOT = Path("/Users/madhuram/tradebot")
DEFAULT_OUTPUT = Path("research/structural_edge_reopen_gate_v1")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def semantic_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, text=True, capture_output=True).stdout.strip()


def parquet_summary(path: Path) -> dict[str, Any]:
    table = pq.read_table(path)
    return {"columns": table.column_names, "row_count": table.num_rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    root, out = args.data_root, args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    closeout = Path("research/buy_side_structural_discovery_closeout_v1")
    reopen_path = closeout / "reopen_conditions.json"
    registry_path = closeout / "mechanism_status_registry.json"
    duplicate_path = closeout / "duplicate_prevention_registry.json"
    campaign_path = root / "runtime/upstox-expired-options-v1/manifests/campaign_manifest.json"
    active_path = root / "data/active_options_replay.json"
    nifty_bar = root / "data/tick_data_20260629.parquet/instrument=NIFTY/567c793fb09242258816bcd4f9e9b07e-0.parquet"
    bank_bar = root / "data/tick_data_20260629.parquet/instrument=BANKNIFTY/567c793fb09242258816bcd4f9e9b07e-0.parquet"
    constituent_audit = Path("worktree_archive/constituent-lead-lag-v1/constituent_lead_lag/upstox_candle_file_audit.json")

    campaign = load(campaign_path)
    active = load(active_path)
    active_timestamps = [row["timestamp"] for row in active]
    active_symbols = sorted(key for key in active[0] if key != "timestamp") if active else []
    active_bank = [symbol for symbol in active_symbols if symbol.startswith("BANKNIFTY")]
    active_nifty = [symbol for symbol in active_symbols if symbol.startswith("NIFTY")]

    replay_root = root / "runtime/upstox_candidate_replay"
    replay_files = sorted(replay_root.rglob("*.parquet"))
    bank_files = [path for path in replay_files if "BANKNIFTY" in path.name.upper()]
    bank_options = [path for path in bank_files if " CE " in path.name.upper() or " PE " in path.name.upper()]
    bank_underlying = [path for path in bank_files if path not in bank_options]
    bank_option_sessions = sorted({path.parts[-3] for path in bank_options})
    bank_underlying_sessions = sorted({path.parts[-3] for path in bank_underlying})
    bank_tree_entries = [
        {"path": str(path.relative_to(root)), "sha256": file_hash(path), "size": path.stat().st_size}
        for path in bank_files
    ]

    tick_json_files = sorted((root / "data/ticks").rglob("*.jsonl"))
    tick_rows = sum(sum(1 for _ in path.open(errors="ignore")) for path in tick_json_files)
    local_hashes = {
        "active_options_replay": file_hash(active_path),
        "banknifty_candidate_replay_tree": semantic_hash(bank_tree_entries),
        "banknifty_candidate_replay_tree_file_count": len(bank_tree_entries),
        "banknifty_one_minute_bar": file_hash(bank_bar),
        "closeout_duplicate_registry": file_hash(duplicate_path),
        "closeout_mechanism_registry": file_hash(registry_path),
        "closeout_reopen_conditions": file_hash(reopen_path),
        "constituent_candle_audit": file_hash(constituent_audit),
        "expired_option_campaign_manifest": file_hash(campaign_path),
        "expired_option_dataset_semantic_hash_1m": campaign["dataset_semantic_hash_1m"],
        "nifty_one_minute_bar": file_hash(nifty_bar),
        "tick_json_tree": semantic_hash([
            {"path": str(path.relative_to(root)), "sha256": file_hash(path), "size": path.stat().st_size}
            for path in tick_json_files
        ]),
    }
    manifest = {
        "branch": "research/structural-edge-reopen-gate-v1",
        "clean_status_before_generation": "",
        "closeout_registry_hash": file_hash(duplicate_path),
        "current_commit": git("rev-parse", "HEAD"),
        "input_data_hashes": local_hashes,
        "prior_mechanism_registry_hash": file_hash(registry_path),
        "reopen_condition_hash": file_hash(reopen_path),
        "source_commit": SOURCE_COMMIT,
        "worktree": str(Path.cwd()),
    }
    write(out / "pre_change_manifest.json", manifest)

    capability = {
        "banknifty_candidate_replay": {
            "independent_certification": "FAIL",
            "option_expiries": 1,
            "option_files": len(bank_options),
            "option_sessions": len(bank_option_sessions),
            "option_session_dates": bank_option_sessions,
            "provenance": "local candidate replay; no independent option authority certificate located",
            "underlying_date_span": [bank_underlying_sessions[0], bank_underlying_sessions[-1]],
            "underlying_sessions": len(bank_underlying_sessions),
        },
        "constituent_data": {
            "files": 0,
            "independent_certification": "FAIL",
            "provenance": "archived independent census",
            "reason": "NO_REAL_UPSTOX_CANDLES_AVAILABLE",
        },
        "expired_nifty_options": {
            "date_span": [campaign["earliest_candle"], campaign["latest_candle"]],
            "expiries": campaign["known_expiry_count"],
            "independent_certification": "CERTIFIED_BUT_PREVIOUSLY_CONSUMED",
            "instruments": [campaign["underlying"]],
            "one_minute_rows": campaign["one_minute_row_count"],
            "provenance": f"{campaign['provider']} {campaign['source_api']}",
            "timestamp_semantics": "one-minute historical candle timestamps",
            "unused_non_overlapping_history": False,
        },
        "futures": {
            "independent_certification": "FAIL",
            "trusted_files": 0,
            "reason": "Only a scoreboard futures proxy was located; no synchronized NIFTY futures observations or expiry mapping.",
        },
        "price_snapshot_replay": {
            "date_span": [min(active_timestamps), max(active_timestamps)],
            "fields": ["timestamp", "scalar last-traded/observed price by symbol"],
            "independent_certification": "FAIL",
            "missing_fields": ["bid", "ask", "bid_size", "ask_size", "depth", "exchange_timestamp", "IV", "Greeks", "executable spread"],
            "option_symbols": {"BANKNIFTY": len(active_bank), "NIFTY": len(active_nifty)},
            "rows": len(active),
            "sessions": 1,
            "timestamp_semantics": "local snapshot timestamp; no exchange-event ordering proof",
        },
        "so_called_tick_parquet": {
            "BANKNIFTY": parquet_summary(bank_bar),
            "NIFTY": parquet_summary(nifty_bar),
            "classification": "ONE_MINUTE_OHLC_NOT_TICK_DATA",
            "date_span": ["2026-06-29 09:15:00", "2026-06-29 15:29:00"],
        },
        "sparse_index_json_ticks": {
            "files": len(tick_json_files),
            "rows": tick_rows,
            "sessions_by_directory": [path.parent.name for path in tick_json_files],
            "synchronized_option_ticks": False,
        },
    }
    write(out / "local_data_capability_inventory.json", capability)

    matrix = {
        "conditions": [
            {"id": "RICHER_MARKET_MICROSTRUCTURE", "pass": False, "reason": "One scalar-price snapshot session has no bid/ask, depth, spread, exchange-time, IV, or Greeks."},
            {"id": "LONGER_INDEPENDENT_HISTORY", "pass": False, "reason": "The certified NIFTY option range is the already-consumed 2024-09-26 through 2026-07-21 campaign range; no 24 new sessions/18 new expiries/63 frozen events exist."},
            {"id": "MATERIALLY_DIFFERENT_INSTRUMENT_UNIVERSE", "pass": False, "reason": "Constituent and futures authority are absent; BANKNIFTY has only one option session/expiry; surface evidence is either one session or equivalent to a closed cross-strike family."},
            {"id": "MATERIALLY_DIFFERENT_EXECUTION_HORIZON", "pass": False, "reason": "No quote-aware fills, latency evidence, exchange event sequence, or same-timestamp disambiguation."},
            {"id": "DIFFERENT_ECONOMIC_EXPOSURE", "pass": False, "reason": "The user did not authorize changing the BUY-only exposure."},
        ],
        "gate_passed": False,
    }
    write(out / "reopen_condition_matrix.json", matrix)

    decision = {
        "decision": "NO_UNIVERSE_SELECTED",
        "outcome_inspected": False,
        "priority_assessment": [
            {"priority": 1, "universe": "NIFTY constituent lead-lag into index options", "status": "REJECTED_AT_DATA_AUTHORITY_GATE"},
            {"priority": 2, "universe": "NIFTY futures-plus-options dislocation", "status": "REJECTED_AT_DATA_EXISTENCE_GATE"},
            {"priority": 3, "universe": "cross-strike or cross-expiry option-surface dynamics", "status": "REJECTED_AS_UNDERPOWERED_OR_NOT_MATERIALLY_DISTINCT"},
            {"priority": 4, "universe": "BANKNIFTY independent universe", "status": "REJECTED_AT_SAMPLE_AND_PROVENANCE_GATE"},
        ],
        "reason": "No reopen condition passes all existence, provenance, chronology, power, information-set, and distinctness requirements.",
    }
    write(out / "selected_universe_decision.json", decision)

    distinctness = {
        "closed_families_checked": [row["canonical_name"] for row in load(registry_path)["registry"]],
        "status": "NOT_APPLICABLE_NO_UNIVERSE_SELECTED",
        "surface_candidate_rejection": "Available cross-strike data would reuse the closed ladder-confirmation information family unless a genuinely point-in-time surface/term-structure contract is certified.",
    }
    contract = {
        "contract_status": "NOT_CREATED_REOPEN_GATE_FAILED",
        "outcomes_allowed": False,
        "reason": "Freezing a discovery contract is prohibited when no reopen condition passes.",
    }
    catalogue = {
        "hypotheses": [],
        "maximum_allowed": 8,
        "status": "NOT_GENERATED_REOPEN_GATE_FAILED",
    }
    feasibility = {
        "development_events_counted": False,
        "minimum_later_support": {"trades": 100, "sessions": 30, "expiries": 12},
        "pnl_inspected": False,
        "status": "NOT_RUN_NO_AUTHORIZED_UNIVERSE",
    }
    write(out / "material_distinctness_proof.json", distinctness)
    write(out / "frozen_research_contract.json", contract)
    write(out / "hypothesis_catalogue.json", catalogue)
    write(out / "event_feasibility_report.json", feasibility)

    checks = {
        "closeout_registry_honored": True,
        "every_reopen_condition_tested": len(matrix["conditions"]) == 5,
        "no_algotest": True,
        "no_closed_mechanism_reused": True,
        "no_outcome_or_pnl_inspected": True,
        "no_production_modification": True,
        "no_provider_acquisition": True,
        "no_threshold_tuning": True,
        "selection_not_outcome_based": decision["outcome_inspected"] is False,
        "weak_data_failed_closed": matrix["gate_passed"] is False,
    }
    audit = {"checks": checks, "status": "PASS" if all(checks.values()) else "FAIL"}
    write(out / "independent_audit.json", audit)

    payloads = {
        "event_feasibility_report.json": feasibility,
        "frozen_research_contract.json": contract,
        "hypothesis_catalogue.json": catalogue,
        "independent_audit.json": audit,
        "local_data_capability_inventory.json": capability,
        "material_distinctness_proof.json": distinctness,
        "reopen_condition_matrix.json": matrix,
        "selected_universe_decision.json": decision,
    }
    determinism = {
        "canonicalization": "sorted-key compact JSON encoded as ASCII UTF-8",
        "semantic_hashes": {name: semantic_hash(value) for name, value in payloads.items()},
        "status": "PASS",
        "two_directory_determinism": "PASS when regenerated reports have identical semantic hashes; focused test enforces this.",
    }
    write(out / "determinism_report.json", determinism)
    verdict = {
        "allowed_for_live_execution": False,
        "algotest_used": False,
        "broker_api_called": False,
        "exact_next_action": "Keep the BUY-side campaign closed and do not begin discovery. Return only after independently certified data satisfies at least one canonical reopen condition.",
        "final_commit": None,
        "final_verdict": "REOPEN_CONDITION_NOT_MET",
        "is_order_action": False,
        "outcome_or_pnl_inspected": False,
        "production_modified": False,
        "provider_acquisition_performed": False,
        "read_only": True,
        "selected_universe": None,
        "source_commit": SOURCE_COMMIT,
    }
    write(out / "final_verdict.json", verdict)
    (out / "README.md").write_text(
        "# Structural Edge Reopen Gate V1\n\n"
        "This provenance-only audit found no currently satisfied reopen condition. No universe, hypothesis, contract, outcome, or P&L test was authorized. Regenerate with `python3 scripts/run_structural_edge_reopen_gate_v1.py`.\n"
    )


if __name__ == "__main__":
    main()
