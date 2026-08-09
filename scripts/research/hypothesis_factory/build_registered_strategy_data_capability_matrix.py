#!/usr/bin/env python3
"""Build a fail-closed data capability matrix for the frozen registered strategy set.

This script is research-only. It does not backtest, place orders, or mutate strategy
logic. It verifies the frozen underlying datasets, inspects whether nominal volume
and quote columns contain usable observations, scans the exact frozen strategy
sources for data-family dependencies, and emits a capability matrix.

A strategy is never marked CERTIFIED here. Output states are only readiness states:
READY_FOR_EDGE_CERTIFICATION, BLOCKED_PENDING_SYNC_DATASET_VERIFICATION,
INSUFFICIENT_EVIDENCE, DEFER_CHILD_CERTIFICATION, or SUPPORT_COMPONENT_EXCLUDED.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "research/evidence/strategy_certification/REGISTERED_ALPHA_FREEZE_MANIFEST_V1.json"
OUT = ROOT / "research/evidence/strategy_certification/REGISTERED_STRATEGY_DATA_CAPABILITY_MATRIX_V1.json"

CANONICAL_PATHS = {
    "NIFTY": ROOT / "research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv",
    "BANKNIFTY": ROOT / "research/hypotheses/historical_corpus/kite_banknifty_cache_v2/canonical/BANKNIFTY.csv",
    "SENSEX": ROOT / "research/hypotheses/historical_corpus/kite_sensex_cache_v2/canonical/SENSEX.csv",
}

META_IDS = {"ensemble", "pro_strategy"}
SYNC_IDS = {"pairs_arbitrage", "volatility_trend"}

# These tokens denote data families that cannot be reconstructed honestly from
# the verified underlying OHLC/VWAP corpus when the corresponding capability is
# absent. Matching is deliberately conservative and only affects readiness.
OPTION_OR_FLOW_TOKENS = {
    "ce_premium_change", "pe_premium_change", "option_ltp", "option_ltp_age_sec",
    "oi_delta", "iv_truth", "depth_truth", "order_flow", "dealer_gamma_exposure",
    "vpin_toxicity", "cumulative_volume_delta", "bid_ask", "option_chain",
}
EVENT_TOKENS = {"event_state", "event_active", "scheduled_event"}
VOLUME_TOKENS = {"volume_z", "volume_ratio", "cumulative_volume_delta", "vpin_toxicity"}
CROSS_ASSET_TOKENS = {"cross_asset_health", "cross_assets", "confirming_assets", "cointegration_truth", "hedge_ratio"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_show(commit: str, path: str) -> str:
    p = subprocess.run(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT,
        check=False, capture_output=True, text=True,
    )
    if p.returncode != 0:
        return ""
    return p.stdout


def module_to_path(module_path: str) -> str:
    return module_path.replace(".", "/") + ".py"


def inspect_csv(path: Path) -> dict:
    result = {
        "path": str(path.relative_to(ROOT)),
        "exists": path.exists(),
        "sha256": None,
        "header": [],
        "rows": 0,
        "nonzero_volume_rows": 0,
        "positive_bid_rows": 0,
        "positive_ask_rows": 0,
        "usable_bid_ask_rows": 0,
        "fallback_true_rows": 0,
    }
    if not path.exists():
        return result
    result["sha256"] = sha256(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        result["header"] = list(reader.fieldnames or [])
        for row in reader:
            result["rows"] += 1
            try:
                vol = float(row.get("volume") or 0)
            except ValueError:
                vol = 0.0
            try:
                bid = float(row.get("bid") or 0)
            except ValueError:
                bid = 0.0
            try:
                ask = float(row.get("ask") or 0)
            except ValueError:
                ask = 0.0
            if vol > 0:
                result["nonzero_volume_rows"] += 1
            if bid > 0:
                result["positive_bid_rows"] += 1
            if ask > 0:
                result["positive_ask_rows"] += 1
            if bid > 0 and ask >= bid:
                result["usable_bid_ask_rows"] += 1
            if str(row.get("is_fallback", "")).strip().lower() in {"true", "1", "yes"}:
                result["fallback_true_rows"] += 1
    return result


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    source_commit = manifest["implementation_source_commit"]

    expected_hash = {}
    for entry in manifest["frozen_dataset_catalog"]:
        if "instrument" in entry:
            expected_hash[entry["instrument"]] = entry["sha256"]

    datasets = {k: inspect_csv(v) for k, v in CANONICAL_PATHS.items()}
    for instrument, info in datasets.items():
        info["expected_sha256"] = expected_hash.get(instrument)
        info["hash_verified"] = bool(info["sha256"] and info["sha256"] == info["expected_sha256"])

    all_hashes_verified = all(v["hash_verified"] for v in datasets.values())
    usable_volume = any(v["nonzero_volume_rows"] > 0 for v in datasets.values())
    usable_quotes = any(v["usable_bid_ask_rows"] > 0 for v in datasets.values())

    sync_entry = next((x for x in manifest["frozen_dataset_catalog"] if x.get("dataset_id") == "BANKNIFTY_NIFTY_SENSEX_SYNC_5M_V1"), None)
    sync_verified = False  # Must be proven against a physical artifact in a later step.

    rows = []
    for spec in manifest["certification_eligible"]:
        sid = spec["strategy_id"]
        path = module_to_path(spec["module_path"])
        source = git_show(source_commit, path)
        source_lower = source.lower()

        hits = {
            "option_or_flow": sorted(t for t in OPTION_OR_FLOW_TOKENS if t.lower() in source_lower),
            "event": sorted(t for t in EVENT_TOKENS if t.lower() in source_lower),
            "volume": sorted(t for t in VOLUME_TOKENS if t.lower() in source_lower),
            "cross_asset": sorted(t for t in CROSS_ASSET_TOKENS if t.lower() in source_lower),
        }

        reasons = []
        if not source:
            status = "INSUFFICIENT_EVIDENCE"
            reasons.append("FROZEN_SOURCE_NOT_READABLE_FROM_GIT_OBJECT")
        elif sid in META_IDS:
            status = "DEFER_CHILD_CERTIFICATION"
            reasons.append("META_STRATEGY_REQUIRES_CERTIFIED_CHILD_EVIDENCE_FIRST")
        elif sid in SYNC_IDS and not sync_verified:
            status = "BLOCKED_PENDING_SYNC_DATASET_VERIFICATION"
            reasons.append("FROZEN_SYNC_DATASET_HASH_NOT_YET_REVERIFIED_AGAINST_PHYSICAL_ARTIFACT")
        elif hits["event"]:
            status = "INSUFFICIENT_EVIDENCE"
            reasons.append("EVENT_STATE_NOT_PRESENT_IN_VERIFIED_UNDERLYING_CORPUS")
        elif hits["option_or_flow"]:
            status = "INSUFFICIENT_EVIDENCE"
            reasons.append("OPTION_OR_MICROSTRUCTURE_INPUTS_NOT_PRESENT_IN_VERIFIED_UNDERLYING_CORPUS")
        elif hits["volume"] and not usable_volume:
            status = "INSUFFICIENT_EVIDENCE"
            reasons.append("SOURCE_CONSUMES_VOLUME_DERIVED_INPUTS_BUT_VERIFIED_CORPUS_HAS_NO_USABLE_VOLUME")
        elif not all_hashes_verified:
            status = "INSUFFICIENT_EVIDENCE"
            reasons.append("ONE_OR_MORE_FROZEN_UNDERLYING_HASHES_FAILED")
        else:
            status = "READY_FOR_EDGE_CERTIFICATION"
            reasons.append("FROZEN_SOURCE_DEPENDENCIES_APPEAR_RECONSTRUCTIBLE_FROM_VERIFIED_OHLC_VWAP_CORPUS")

        rows.append({
            "strategy_id": sid,
            "module_path": spec["module_path"],
            "callable_name": spec["callable_name"],
            "source_path": path,
            "source_present_at_frozen_commit": bool(source),
            "dependency_token_hits": hits,
            "readiness": status,
            "reasons": reasons,
        })

    for sid in manifest["support_component_ids"]:
        rows.append({
            "strategy_id": sid,
            "readiness": "SUPPORT_COMPONENT_EXCLUDED",
            "reasons": ["STRUCTURAL_GATE_EXCLUDES_SUPPORT_COMPONENT_FROM_STANDALONE_ALPHA_CERTIFICATION"],
        })

    counts = {}
    for row in rows:
        counts[row["readiness"]] = counts.get(row["readiness"], 0) + 1

    payload = {
        "schema_version": 1,
        "matrix_id": "REGISTERED_STRATEGY_DATA_CAPABILITY_MATRIX_V1",
        "research_only": True,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "source_commit": source_commit,
        "freeze_manifest_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dataset_summary": datasets,
        "aggregate_capabilities": {
            "all_underlying_hashes_verified": all_hashes_verified,
            "usable_nonzero_volume_present": usable_volume,
            "usable_bid_ask_present": usable_quotes,
            "sync_dataset_declared": bool(sync_entry),
            "sync_dataset_physical_hash_verified": sync_verified,
        },
        "readiness_counts": counts,
        "rows": rows,
        "interpretation": "READY_FOR_EDGE_CERTIFICATION IS NOT A PROFITABILITY OR EDGE VERDICT. IT ONLY MEANS THE CURRENT FROZEN DATA APPEARS SUFFICIENT TO RUN THE NEXT CERTIFICATION STAGE WITHOUT SYNTHETIC INPUTS.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "output": str(OUT),
        "source_commit": source_commit,
        "all_underlying_hashes_verified": all_hashes_verified,
        "usable_nonzero_volume_present": usable_volume,
        "usable_bid_ask_present": usable_quotes,
        "sync_dataset_physical_hash_verified": sync_verified,
        "readiness_counts": counts,
        "runtime_authority": "NONE",
        "status": "CAPABILITY_MATRIX_BUILT",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
