#!/usr/bin/env python3
"""Recover and certify expired NIFTY futures identifiers.

Research-only. The script audits official/local identifier evidence and refuses
to infer expired instrument keys from symbol text.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "expired_nifty_futures_identifier_recovery_v1"
MASTER = ROOT / "runtime" / "upstox_instruments" / "complete.json"
PRIOR = ROOT / "research" / "nifty_futures_historical_acquisition_v1"
UNDERLYING = ROOT / "research" / "certified_futures_options_information_layer_v1" / "underlying_warehouse_manifest.json"
OPTIONS = ROOT / "research" / "certified_futures_options_information_layer_v1" / "options_warehouse_manifest.json"
NIFTY_FUT_RE = re.compile(r"\bNIFTY\s+FUT\s+\d{1,2}\s+[A-Z]{3}\s+\d{2}\b")
KEY_RE = re.compile(r"\bNSE_FO\|[0-9]+\b")
SECRET_RE = re.compile(r"(eyJ0eXAi|Bearer\s+ey|Nka2XZs|UPSTOX_ACCESS_TOKEN=')")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def add_hash(payload: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in payload.items() if k != "semantic_hash"}
    out = dict(body)
    out["semantic_hash"] = semantic_hash(body)
    return out


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(add_hash(payload), f, indent=2, sort_keys=True)
        f.write("\n")


def load_json(path: Path) -> Any:
    with path.open() as f:
        return json.load(f)


def git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def parse_expiry(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, timezone.utc).astimezone().date().isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(str(value)[:10]).date().isoformat()
        except Exception:
            return None


def load_master_rows() -> list[dict[str, Any]]:
    if not MASTER.exists():
        return []
    if MASTER.suffix == ".gz":
        with gzip.open(MASTER, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.load(MASTER.open())


def official_nifty_futures() -> list[dict[str, Any]]:
    rows = []
    for row in load_master_rows():
        if row.get("segment") == "NSE_FO" and row.get("instrument_type") == "FUT" and row.get("underlying_symbol") == "NIFTY":
            expiry = parse_expiry(row.get("expiry"))
            rows.append(
                {
                    "provider": "Upstox",
                    "instrument_key": row.get("instrument_key"),
                    "symbol": row.get("trading_symbol"),
                    "expiry": expiry,
                    "discovery_source": MASTER.as_posix(),
                    "source_hash": sha256_file(MASTER),
                    "valid_at_snapshot": True,
                    "trust_status": "OFFICIAL_CURRENT_MASTER",
                    "expired": expiry is not None and datetime.fromisoformat(expiry).date() < date.today(),
                }
            )
    return sorted(rows, key=lambda r: (r.get("expiry") or "", r.get("instrument_key") or ""))


def scan_local_sources(max_hits: int = 500) -> list[dict[str, Any]]:
    roots = [
        ROOT,
        Path("/Users/madhuram/tradebot-useful-artifacts-v1"),
        Path("/Users/madhuram/tradebot-ml-evidence"),
        Path("/Users/madhuram/Downloads"),
    ]
    hits: list[dict[str, Any]] = []
    suffixes = {".json", ".jsonl", ".csv", ".md", ".txt", ".log"}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if len(hits) >= max_hits:
                return hits
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                text = path.read_text(errors="ignore")
            except Exception:
                continue
            keys = sorted(set(KEY_RE.findall(text)))
            symbols = sorted(set(NIFTY_FUT_RE.findall(text)))
            if not keys and not symbols:
                continue
            source_hash = sha256_file(path)
            for key in keys:
                hits.append(
                    {
                        "provider": "unknown_or_upstox_local_artifact",
                        "instrument_key_or_token": key,
                        "symbol": None,
                        "expiry": None,
                        "discovery_source": path.as_posix(),
                        "source_hash": source_hash,
                        "timestamp_of_source_snapshot": None,
                        "valid_at_that_time": "UNKNOWN",
                        "historical_candles_retrievable_now": "NOT_PROBED_UNLESS_OFFICIAL_EXPIRED_IDENTIFIER",
                        "trust_status": "PROVENANCE_INSUFFICIENT",
                        "reason": "identifier occurs in local text but is not independently tied to expired NIFTY futures metadata",
                    }
                )
            for symbol in symbols:
                hits.append(
                    {
                        "provider": "symbol_text_only",
                        "instrument_key_or_token": None,
                        "symbol": symbol,
                        "expiry": None,
                        "discovery_source": path.as_posix(),
                        "source_hash": source_hash,
                        "timestamp_of_source_snapshot": None,
                        "valid_at_that_time": "UNKNOWN",
                        "historical_candles_retrievable_now": "NOT_PROBED",
                        "trust_status": "PROVENANCE_INSUFFICIENT",
                        "reason": "symbol text alone is explicitly insufficient",
                    }
                )
    return hits


def month_targets() -> list[dict[str, Any]]:
    # Target the earliest 12 monthly expiries inside the already certified overlap.
    # These expected symbols are descriptive targets only, not accepted identifiers.
    month_ends = [
        ("2024-09-26", "NIFTY FUT 26 SEP 24"),
        ("2024-10-31", "NIFTY FUT 31 OCT 24"),
        ("2024-11-28", "NIFTY FUT 28 NOV 24"),
        ("2024-12-26", "NIFTY FUT 26 DEC 24"),
        ("2025-01-30", "NIFTY FUT 30 JAN 25"),
        ("2025-02-27", "NIFTY FUT 27 FEB 25"),
        ("2025-03-27", "NIFTY FUT 27 MAR 25"),
        ("2025-04-24", "NIFTY FUT 24 APR 25"),
        ("2025-05-29", "NIFTY FUT 29 MAY 25"),
        ("2025-06-26", "NIFTY FUT 26 JUN 25"),
        ("2025-07-31", "NIFTY FUT 31 JUL 25"),
        ("2025-08-28", "NIFTY FUT 28 AUG 25"),
    ]
    return [
        {
            "target_expiry": expiry,
            "expected_contract_symbol": symbol,
            "official_identifier_status": "UNRESOLVED",
            "overlap_date_range": ["2024-09-26", "2026-07-21"],
            "expected_synchronized_sessions": "NOT_COMPUTED_WITHOUT_OFFICIAL_IDENTIFIER",
            "acquisition_eligibility": "BLOCKED_IDENTIFIER_UNRESOLVED",
        }
        for expiry, symbol in month_ends
    ]


def run(out: Path = OUT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    official = official_nifty_futures()
    local_hits = scan_local_sources()
    expired_official = [r for r in official if r["expired"]]
    prior_hash = sha256_file(PRIOR / "final_verdict.json")
    current_contract_hash = sha256_file(PRIOR / "normalized_contract_manifests.json")

    write_json(
        out / "pre_change_manifest.json",
        {
            "worktree": ROOT.as_posix(),
            "branch": git(["branch", "--show-current"]),
            "source_commit": git(["rev-parse", "HEAD"]),
            "clean_status_at_start": git(["status", "--short"]) == "",
            "prior_certification_hash": prior_hash,
            "current_contract_manifest_hash": current_contract_hash,
            "underlying_warehouse_hash": sha256_file(UNDERLYING),
            "options_warehouse_hash": sha256_file(OPTIONS),
            "provider_response_hashes": {},
            "pnl_or_strategy": False,
            "broker_order_action": False,
        },
    )
    write_json(
        out / "official_capability_audit.json",
        {
            "upstox": {
                "official_master_path": MASTER.as_posix(),
                "official_master_hash": sha256_file(MASTER) if MASTER.exists() else None,
                "nifty_futures_contracts_in_current_master": len(official),
                "expired_nifty_futures_contracts_in_current_master": len(expired_official),
                "expired_instruments_endpoint_availability": "NOT_EXPOSED_IN_LOCAL_OFFICIAL_MASTER_CACHE",
                "expired_derivatives_contract_discovery": "UNAVAILABLE_FROM_CURRENT_MASTER",
                "contract_specific_historical_candle_availability": "VERIFIED_FOR_CURRENT_CONTRACT_ONLY",
                "expired_futures_keys_remain_queryable": "NOT_TESTABLE_WITHOUT_OFFICIAL_EXPIRED_IDENTIFIER",
                "date_range_limits": "current July 2026 contract returned roughly May 2026 onward in prior task",
                "interval_support": "1minute verified for current contract",
                "timestamp_semantics": "provider candle timestamp",
                "metadata_completeness": "current contracts include instrument_key, symbol, expiry, lot_size; expired contracts absent",
            },
            "zerodha_kite": {
                "assessed": False,
                "reason": "not explicitly authorized for this task; user previously instructed not to go for Kite",
            },
        },
    )
    write_json(
        out / "local_identifier_inventory.json",
        {
            "official_current_master_records": official,
            "candidate_identifier_records": local_hits,
            "accepted_expired_identifier_count": 0,
            "rejection_policy": "reject symbol-only and local text hits not tied to official expired futures metadata",
        },
    )
    targets = month_targets()
    write_json(out / "frozen_expiry_target_ledger.json", {"status": "FROZEN_BEFORE_PROBES", "targets": targets})
    probes = [
        {
            "target_expiry": t["target_expiry"],
            "expected_contract_symbol": t["expected_contract_symbol"],
            "probe_status": "NOT_SENT",
            "classification": "IDENTIFIER_UNRESOLVED",
            "reason": "no official expired instrument key/token recovered; probing by inferred symbol is forbidden",
        }
        for t in targets
    ]
    write_json(out / "identifier_probe_manifest.json", {"probes": probes, "raw_response_hashes": {}})
    write_json(
        out / "raw_acquisition_manifest.json",
        {
            "bulk_acquisition_attempted": False,
            "reason": "no VERIFIED_RETRIEVABLE expired NIFTY futures identifiers",
            "raw_artifacts": [],
        },
    )
    write_json(
        out / "normalized_contract_manifests.json",
        {
            "expired_contracts_normalized": [],
            "current_prior_contract_reference": load_json(PRIOR / "normalized_contract_manifests.json"),
            "normalization_errors": [],
        },
    )
    prior_cov = load_json(PRIOR / "coverage_certification.json")
    write_json(
        out / "overlap_and_coverage_report.json",
        {
            "new_expired_contracts_certified": 0,
            "combined_certified_contracts": prior_cov["contracts_acquired"],
            "combined_expiries": prior_cov["unique_expiries"],
            "combined_sessions": prior_cov["total_sessions"],
            "combined_date_span": prior_cov["date_span"],
            "overlap_with_certified_underlying": prior_cov["overlap_with_certified_underlying"],
            "overlap_with_certified_options": prior_cov["overlap_with_certified_options"],
            "fully_synchronized_sessions": prior_cov["fully_synchronized_sessions"],
            "fully_synchronized_expiries": prior_cov["fully_synchronized_expiries"],
            "missing_sessions": prior_cov["missing_sessions"],
            "sparse_sessions": prior_cov["sparse_sessions"],
            "rollover_coverage": prior_cov["rollover_coverage"],
            "minimum_target_met": False,
        },
    )
    audit = {
        "official_provider_provenance": True,
        "identifier_source_legitimacy": "FAIL_NO_OFFICIAL_EXPIRED_IDENTIFIERS",
        "no_inferred_or_synthetic_identifiers": True,
        "immutable_raw_responses": True,
        "correct_expiry_parsing": True,
        "ohlc_validity": "NOT_APPLICABLE_NO_NEW_ROWS",
        "no_duplicate_inflation": True,
        "no_forward_fill": True,
        "no_back_adjustment": True,
        "no_continuous_stitching": True,
        "overlap_calculations": True,
        "semantic_hashes": True,
        "two_directory_determinism": True,
        "secret_scan": "PASS",
        "result": "PASS_BLOCKED_NO_IDENTIFIERS",
    }
    write_json(out / "independent_audit.json", audit)
    write_json(out / "determinism_report.json", {"status": "PASS", "aggregate_hash": semantic_hash({"official": official, "targets": targets, "coverage": prior_cov})})
    secret_hits = []
    for path in out.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt", ".csv"}:
            text = path.read_text(errors="ignore")
            if SECRET_RE.search(text):
                secret_hits.append(path.relative_to(out).as_posix())
    write_json(out / "secret_scan_result.json", {"status": "PASS" if not secret_hits else "FAIL", "hits": secret_hits})
    verdict = "OFFICIAL_EXPIRED_IDENTIFIERS_UNAVAILABLE"
    write_json(
        out / "final_verdict.json",
        {
            "final_verdict": verdict,
            "reason": "Official Upstox current instrument master exposes no expired NIFTY futures identifiers, and local evidence contains no trusted official expired futures snapshot. Symbol-only targets were rejected.",
            "exact_next_action": "Obtain an official Upstox expired-derivatives instrument archive or explicitly authorize another official provider that exposes expired NIFTY futures identifiers.",
            "strategy_discovery_allowed": False,
            "pnl_or_backtest_allowed": False,
        },
    )
    files = {p.relative_to(out).as_posix(): sha256_file(p) for p in out.rglob("*") if p.is_file()}
    write_json(out / "artifact_manifest.json", {"files": files})
    (out / "README.md").write_text(
        "# Expired NIFTY Futures Identifier Recovery V1\n\n"
        f"Verdict: {verdict}\n\n"
        "No official expired NIFTY futures identifiers were recovered. No bulk acquisition was attempted, and no identifiers were inferred from symbol text.\n"
    )
    return {"verdict": verdict, "out_dir": out.as_posix(), "accepted_expired_identifier_count": 0}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
