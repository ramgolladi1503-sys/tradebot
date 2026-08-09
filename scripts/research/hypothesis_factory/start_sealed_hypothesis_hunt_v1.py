#!/usr/bin/env python3
"""Bootstrap the next strategy hypothesis hunt under the sealed certification kernel.

This stage does NOT backtest, read holdout outcomes, tune parameters, or claim edge.
It inventories local domain-closure evidence, compares a small set of causal
price-only hypothesis seeds against prior closed work, and emits freeze-ready
candidates only when novelty is not contradicted by repository/local evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SEALED_KERNEL_COMMIT = "46dd4f7df9b63486eb633a12baf25412cd4f761d"
SEALED_KERNEL_RUNNER_SHA256 = "b27ac20068aa399ca1bc2ba9b56d9192089b9cc02f52903fa758b2ef00bf9c91"
SYNC_DATASET_SHA256 = "66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32"

SEEDS = [
    {
        "hypothesis_id": "HUNT_V1_LEADER_CONSENSUS_LAG_CATCHUP",
        "family": "CROSS_MARKET_LEADER_LAG",
        "summary": "When NIFTY and SENSEX agree directionally but BANKNIFTY materially lags their contemporaneous move, BANKNIFTY catches up over subsequent completed bars.",
        "required_fields": ["banknifty_ret_1_bps", "nifty_ret_1_bps", "sensex_ret_1_bps", "leaders_consensus"],
        "entry_timing": "DECISION_ON_COMPLETED_BAR_T_ENTRY_NO_EARLIER_THAN_T_PLUS_1",
        "economics": "BANKNIFTY_UNDERLYING_DIRECTIONAL_RETURN_ONLY",
    },
    {
        "hypothesis_id": "HUNT_V1_FROM_OPEN_RELATIVE_STRENGTH_PERSISTENCE",
        "family": "CROSS_MARKET_RELATIVE_STRENGTH",
        "summary": "Persistent agreement in NIFTY and SENSEX from-open direction, combined with BANKNIFTY relative strength in the same direction, predicts short-horizon BANKNIFTY continuation.",
        "required_fields": ["banknifty_from_open_bps", "nifty_from_open_bps", "sensex_from_open_bps"],
        "entry_timing": "DECISION_ON_COMPLETED_BAR_T_ENTRY_NO_EARLIER_THAN_T_PLUS_1",
        "economics": "BANKNIFTY_UNDERLYING_DIRECTIONAL_RETURN_ONLY",
    },
    {
        "hypothesis_id": "HUNT_V1_TRANSIENT_DIVERGENCE_MEAN_REVERSION",
        "family": "CROSS_MARKET_DIVERGENCE_REVERSION",
        "summary": "An extreme one-bar BANKNIFTY divergence from both NIFTY and SENSEX that is not confirmed by from-open relative strength mean-reverts over subsequent bars.",
        "required_fields": ["bn_minus_nifty_bps", "bn_minus_sensex_bps", "banknifty_from_open_bps", "nifty_from_open_bps", "sensex_from_open_bps"],
        "entry_timing": "DECISION_ON_COMPLETED_BAR_T_ENTRY_NO_EARLIER_THAN_T_PLUS_1",
        "economics": "BANKNIFTY_UNDERLYING_DIRECTIONAL_RETURN_ONLY",
    },
    {
        "hypothesis_id": "HUNT_V1_LEADER_REVERSAL_TRANSMISSION",
        "family": "CROSS_MARKET_REVERSAL_TRANSMISSION",
        "summary": "A synchronized reversal in both NIFTY and SENSEX after a sustained from-open move precedes a same-direction BANKNIFTY reversal on subsequent bars.",
        "required_fields": ["nifty_ret_1_bps", "sensex_ret_1_bps", "nifty_from_open_bps", "sensex_from_open_bps", "banknifty_from_open_bps"],
        "entry_timing": "DECISION_ON_COMPLETED_BAR_T_ENTRY_NO_EARLIER_THAN_T_PLUS_1",
        "economics": "BANKNIFTY_UNDERLYING_DIRECTIONAL_RETURN_ONLY",
    },
    {
        "hypothesis_id": "HUNT_V1_DISAGREEMENT_RESOLUTION",
        "family": "CROSS_MARKET_DISAGREEMENT",
        "summary": "When NIFTY and SENSEX disagree on the current bar but their from-open directions agree, BANKNIFTY subsequently resolves toward the shared from-open direction rather than the noisy current-bar disagreement.",
        "required_fields": ["leaders_consensus", "nifty_from_open_bps", "sensex_from_open_bps", "banknifty_ret_1_bps"],
        "entry_timing": "DECISION_ON_COMPLETED_BAR_T_ENTRY_NO_EARLIER_THAN_T_PLUS_1",
        "economics": "BANKNIFTY_UNDERLYING_DIRECTIONAL_RETURN_ONLY",
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(text: str) -> set[str]:
    stop = {"the","and","or","a","an","to","of","in","on","for","with","when","both","same","direction","subsequent","bar","bars"}
    return {x for x in re.findall(r"[a-z0-9_]+", text.lower()) if len(x) > 2 and x not in stop}


def flatten_strings(x: Any) -> list[str]:
    out: list[str] = []
    if isinstance(x, dict):
        for k, v in x.items():
            out.append(str(k)); out.extend(flatten_strings(v))
    elif isinstance(x, list):
        for v in x: out.extend(flatten_strings(v))
    elif isinstance(x, (str, int, float, bool)):
        out.append(str(x))
    return out


def load_closures(root: Path) -> list[dict[str, Any]]:
    base = root / "research/hypotheses/domain_closures"
    docs = []
    if not base.exists():
        return docs
    for path in sorted(base.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        docs.append({
            "path": str(path.relative_to(root)),
            "sha256": sha256(path),
            "text": " ".join(flatten_strings(payload)),
        })
    return docs


def overlap(seed: dict[str, Any], closure: dict[str, Any]) -> float:
    a = tokens(seed["hypothesis_id"] + " " + seed["family"] + " " + seed["summary"])
    b = tokens(closure["text"])
    if not a or not b: return 0.0
    return len(a & b) / len(a)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--dataset", default="research/hypotheses/cross_market/BANKNIFTY_NIFTY_SENSEX.csv")
    p.add_argument("--output", default="research/evidence/strategy_certification/SEALED_HYPOTHESIS_HUNT_V1_BOOTSTRAP.json")
    a = p.parse_args(argv)
    root = Path(a.repo_root).resolve(); ds = root / a.dataset; out = root / a.output
    result = {"status":"FAIL_CLOSED","runtime_authority":"NONE","broker_actions_permitted":False,"edge_claimed":False}
    try:
        if not ds.exists(): raise ValueError("sync_dataset_missing")
        if sha256(ds) != SYNC_DATASET_SHA256: raise ValueError("sync_dataset_hash_mismatch")
        closures = load_closures(root)
        assessed = []
        for seed in SEEDS:
            matches = sorted(
                ({"path": c["path"], "sha256": c["sha256"], "overlap": round(overlap(seed,c),4)} for c in closures),
                key=lambda x: x["overlap"], reverse=True,
            )
            top = matches[:5]
            max_overlap = top[0]["overlap"] if top else 0.0
            # Conservative novelty gate. >=0.50 means prior closure language covers
            # at least half of the seed's meaningful tokens; do not recycle it.
            status = "NOVELTY_REVIEW_REQUIRED" if 0.30 <= max_overlap < 0.50 else ("EXCLUDED_PRIOR_DOMAIN_OVERLAP" if max_overlap >= 0.50 else "FREEZE_READY")
            assessed.append({**seed, "novelty_status": status, "max_prior_overlap": max_overlap, "top_prior_matches": top})
        freeze_ready = [x for x in assessed if x["novelty_status"] == "FREEZE_READY"]
        review = [x for x in assessed if x["novelty_status"] == "NOVELTY_REVIEW_REQUIRED"]
        result.update({
            "status":"HYPOTHESIS_HUNT_BOOTSTRAP_COMPLETE",
            "sealed_kernel_commit":SEALED_KERNEL_COMMIT,
            "sealed_kernel_runner_sha256":SEALED_KERNEL_RUNNER_SHA256,
            "dataset_sha256":sha256(ds),
            "domain_closure_files_seen":len(closures),
            "candidates_total":len(assessed),
            "freeze_ready_count":len(freeze_ready),
            "novelty_review_required_count":len(review),
            "excluded_prior_overlap_count":len(assessed)-len(freeze_ready)-len(review),
            "candidates":assessed,
            "holdout_accessed":False,
            "parameters_tuned":False,
            "edge_claimed":False,
            "runtime_authority":"NONE",
            "broker_actions_permitted":False,
            "next_action":"FREEZE_ONLY_FREEZE_READY_CANDIDATES; MANUALLY_REVIEW_NOVELTY_REVIEW_REQUIRED; DO_NOT_BACKTEST_EXCLUDED_PRIOR_DOMAIN_OVERLAP",
        })
    except Exception as e:
        result["error"] = f"{type(e).__name__}:{e}"
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
    return 0 if result.get("status")=="HYPOTHESIS_HUNT_BOOTSTRAP_COMPLETE" else 2

if __name__ == "__main__": raise SystemExit(main())
