from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "research" / "opening_range_retest_underlying_edge"
VALIDATED_SOURCE = "cf1b63908c779db844ef3534804142a8af26cbac"
PARENT_RESEARCH_COMMIT = "162ae124bd1886e9e780f48e4a3ab743ec8a11e0"
CANDIDATE_LEDGER = PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_causal_replay_candidate_ledger_v2.json"
OUTCOME_LEDGER = PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_outcome_ledger_v2.json"
OUTCOME_SUMMARY = PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_outcome_summary_v2.json"
OUTCOME_CONTRACT = PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_outcome_contract_v2.json"
OUTCOME_AUDIT = PROJECT_ROOT / "docs/agent_reviews/opening_range_retest_outcome_audit_v2.json"
SOURCE_FILES = [CANDIDATE_LEDGER, OUTCOME_LEDGER, OUTCOME_SUMMARY, OUTCOME_CONTRACT, OUTCOME_AUDIT]
PRODUCTION_PREFIXES = ("strategies/", "core/", "config/", "execution/", "risk/", "feeds/")
PRIMARY_HORIZON = "15"
SECONDARY_HORIZONS = ("1", "3", "5", "30")
BOOTSTRAP_SEED = 2026072101
CONTROL_SEED = 2026072102
BOOTSTRAP_RESAMPLES = 10_000
CONTROL_PERMUTATIONS = 2_000


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_bytes(payload) + b"\n"
    path.write_bytes(data)
    digest = sha256_bytes(data)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def write_md(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    digest = sha256_file(path)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def git(args: list[str]) -> str:
    return subprocess.run(args, cwd=PROJECT_ROOT, check=True, capture_output=True, text=True).stdout.strip()


def git_ok(args: list[str]) -> bool:
    return subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True, text=True).returncode == 0


def safety() -> dict[str, Any]:
    return {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "option_pnl_calculated": False,
    }


def mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 12) if values else None


def median(values: list[float]) -> float | None:
    return round(statistics.median(values), 12) if values else None


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("empty_percentile")
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo))


def rankdata(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = rank
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return round(num / (denx * deny), 12)


def spearman(records: list[dict[str, Any]]) -> float | None:
    pairs = [(float(r["score"]), float(r["primary_return"])) for r in records]
    if len(pairs) < 2:
        return None
    return pearson(rankdata([p[0] for p in pairs]), rankdata([p[1] for p in pairs]))


def source_identity() -> dict[str, Any]:
    head = git(["git", "rev-parse", "HEAD"])
    changed = [p for p in git(["git", "diff", "--name-only", f"{VALIDATED_SOURCE}..HEAD"]).splitlines() if p]
    prod_changed = [p for p in changed if p.startswith(PRODUCTION_PREFIXES)]
    working_prod = [
        p for p in git(["git", "diff", "--name-only", VALIDATED_SOURCE, "--", *PRODUCTION_PREFIXES]).splitlines() if p
    ]
    result = {
        "validated_production_source": VALIDATED_SOURCE,
        "research_execution_head": head,
        "research_branch": git(["git", "branch", "--show-current"]),
        "validated_source_is_ancestor": git_ok(["git", "merge-base", "--is-ancestor", VALIDATED_SOURCE, "HEAD"]),
        "production_paths_changed_since_validated_source": prod_changed,
        "working_tree_production_diffs_vs_validated_source": working_prod,
        **safety(),
    }
    result["decision"] = (
        "PASS"
        if result["validated_source_is_ancestor"] and not prod_changed and not working_prod
        else "FAIL"
    )
    if result["decision"] != "PASS":
        raise RuntimeError(f"SOURCE_IDENTITY_FAILED {json.dumps(result, sort_keys=True)}")
    return result


def load_sources() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    return tuple(read_json(path) for path in SOURCE_FILES)  # type: ignore[return-value]


def audit_inputs() -> dict[str, Any]:
    candidate, outcome, summary, contract, audit = load_sources()
    candidate_ids = [r["candidate_id"] for r in candidate["records"]]
    outcome_ids = [r["candidate_id"] for r in outcome["records"]]
    cset = set(candidate_ids)
    oset = set(outcome_ids)
    cores = [r["candidate_core"] for r in candidate["records"]]
    primary_status = Counter(str(r["horizons"][PRIMARY_HORIZON]["status"]) for r in outcome["records"])
    horizons = sorted(str(h) for h in contract.get("horizons_minutes", []))
    result = {
        "source_files": [
            {
                "path": str(path.relative_to(PROJECT_ROOT)),
                "physical_sha256": sha256_file(path),
                "schema_version": read_json(path).get("schema_version"),
                "recorded_semantic_hashes": {
                    key: value for key, value in read_json(path).items() if "hash" in key.lower()
                },
            }
            for path in SOURCE_FILES
        ],
        "candidate_count": len(candidate_ids),
        "outcome_count": len(outcome_ids),
        "unique_candidate_count": len(cset),
        "unique_outcome_count": len(oset),
        "duplicate_candidate_ids": len(candidate_ids) - len(cset),
        "duplicate_outcome_ids": len(outcome_ids) - len(oset),
        "intersection_count": len(cset & oset),
        "candidate_ids_missing_outcomes": sorted(cset - oset),
        "outcome_ids_missing_candidates": sorted(oset - cset),
        "session_count": len({c["session_date"] for c in cores}),
        "date_range": [min(c["session_date"] for c in cores), max(c["session_date"] for c in cores)],
        "symbol_counts": dict(sorted(Counter(c["symbol"] for c in cores).items())),
        "call_count": sum(1 for c in cores if c["direction"] == "BUY_CALL"),
        "put_count": sum(1 for c in cores if c["direction"] == "BUY_PUT"),
        "legal_entry_fields": sorted({k for r in outcome["records"] for k in r.get("legal_entry", {})}),
        "causal_cutoff_fields": ["proposal_ready_at_iso", "legal_entry.start", "legal_entry.end"],
        "available_outcome_horizons": horizons,
        "missing_horizon_counts": {
            horizon: Counter(str(r["horizons"][horizon]["status"]) for r in outcome["records"])
            for horizon in horizons
        },
        "primary_horizon_status_counts": dict(primary_status),
        "outcome_summary_reconciliation": {
            "candidate_count": summary.get("candidate_count"),
            "horizon_conservation": summary.get("horizon_conservation"),
            "summary_hash": summary.get("summary_hash"),
        },
        "outcome_audit_reconciliation": {
            "verdict": audit.get("verdict"),
            "source_join_verified_count": audit.get("source_join_verified_count"),
            "recomputed_outcome_ledger_hash": audit.get("recomputed_outcome_ledger_hash"),
        },
        **safety(),
    }
    result["decision"] = (
        "PASS"
        if result["candidate_count"] == 2215
        and result["duplicate_candidate_ids"] == 0
        and result["duplicate_outcome_ids"] == 0
        and result["intersection_count"] == 2215
        and not result["candidate_ids_missing_outcomes"]
        and not result["outcome_ids_missing_candidates"]
        and PRIMARY_HORIZON in horizons
        and primary_status.get("MEASURED", 0) >= 300
        else "FAIL"
    )
    if result["decision"] != "PASS":
        raise RuntimeError("BLOCKED_INPUT_JOIN_OR_CAUSALITY_FAILURE")
    return result


def build_contract(input_audit: dict[str, Any]) -> dict[str, Any]:
    _, _, _, outcome_contract, _ = load_sources()
    if 15 not in outcome_contract.get("horizons_minutes", []):
        raise RuntimeError("BLOCKED_PRIMARY_HORIZON_NOT_CONTRACT_VALID")
    sessions = sorted(read_joined(include_unmeasured=True).keys())
    dev_count = math.floor(len(sessions) * 0.8)
    dev_sessions = sessions[:dev_count]
    holdout_sessions = sessions[dev_count:]
    blocks = split_blocks(dev_sessions, 6)
    contract = {
        "schema_version": 1,
        "mode": "ORB_CORRECTED_UNDERLYING_EDGE_WFA_AND_HOLDOUT",
        "decision": "UNDERLYING_EDGE_CONTRACT_FROZEN",
        "candidate_universe": "current certified corrected candidate universe",
        "candidate_conservation_against_baseline": "NOT_EVALUATED_DUAL_REPLAY_UNAVAILABLE",
        "primary_horizon": "15-minute direction-normalized underlying return",
        "primary_horizon_contract": {
            "measured_from_legal_entry": True,
            "causal": True,
            "session_contained": True,
            "row_level_available": True,
            "terminal_rule": outcome_contract.get("horizon_terminal_rule", {}).get(PRIMARY_HORIZON),
            "contract_hash": outcome_contract.get("contract_hash"),
        },
        "secondary_horizons": list(SECONDARY_HORIZONS),
        "chronological_split": {
            "session_count": len(sessions),
            "development_session_count": len(dev_sessions),
            "holdout_session_count": len(holdout_sessions),
            "development_range": [dev_sessions[0], dev_sessions[-1]],
            "holdout_range": [holdout_sessions[0], holdout_sessions[-1]],
            "random_split": "FORBIDDEN",
        },
        "development_wfa_blocks": [
            {"block": i + 1, "session_count": len(block), "range": [block[0], block[-1]]}
            for i, block in enumerate(blocks)
        ],
        "score_selection": {
            "top_bucket": "score >= training-set 80th percentile",
            "bottom_bucket": "score <= training-set 20th percentile",
            "validation_threshold_source": "training sessions only",
            "holdout_threshold_source": "full development sessions only",
            "ties": "included",
        },
        "minimum_sample_requirements": {
            "eligible_candidates": 300,
            "sessions": 50,
            "aggregate_oos_top_bucket_candidates": 100,
            "aggregate_oos_bottom_bucket_candidates": 100,
            "both_call_and_put_represented": True,
            "max_single_session_concentration": 0.2,
        },
        "input_audit_decision": input_audit["decision"],
        **safety(),
    }
    contract["contract_hash"] = sha256_bytes(canonical_bytes({k: v for k, v in contract.items() if k != "contract_hash"}))
    return contract


def read_joined(include_unmeasured: bool = False) -> dict[str, list[dict[str, Any]]]:
    candidate, outcome, *_ = load_sources()
    by_candidate = {r["candidate_id"]: r for r in candidate["records"]}
    if len(by_candidate) != len(candidate["records"]):
        raise RuntimeError("duplicate_candidate_ids")
    joined: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen = set()
    for row in outcome["records"]:
        cid = row["candidate_id"]
        if cid in seen:
            raise RuntimeError("duplicate_outcome_ids")
        seen.add(cid)
        if cid not in by_candidate:
            raise RuntimeError("outcome_id_missing_candidate")
        core = row["candidate_core"]
        horizon = row["horizons"][PRIMARY_HORIZON]
        if not include_unmeasured and horizon["status"] != "MEASURED":
            continue
        joined[core["session_date"]].append(
            {
                "candidate_id": cid,
                "session_date": core["session_date"],
                "symbol": core["symbol"],
                "direction": core["direction"],
                "legal_entry_timestamp": row.get("legal_entry", {}).get("start"),
                "score": float(core["raw_score"]),
                "primary_return": float(horizon.get("directional_underlying_return", 0.0)) if horizon["status"] == "MEASURED" else None,
                "primary_status": horizon["status"],
                "secondary_returns": {
                    h: row["horizons"][h].get("directional_underlying_return")
                    for h in SECONDARY_HORIZONS
                    if h in row["horizons"]
                },
                "mfe": horizon.get("mfe"),
                "mae": horizon.get("mae"),
            }
        )
    if set(by_candidate) != seen:
        raise RuntimeError("candidate_id_missing_outcome")
    return dict(joined)


def split_blocks(items: list[str], count: int) -> list[list[str]]:
    base, rem = divmod(len(items), count)
    blocks = []
    start = 0
    for i in range(count):
        size = base + (1 if i < rem else 0)
        blocks.append(items[start : start + size])
        start += size
    return blocks


def flatten(groups: dict[str, list[dict[str, Any]]], sessions: list[str]) -> list[dict[str, Any]]:
    return [record for session in sessions for record in groups.get(session, []) if record["primary_return"] is not None]


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    vals = [float(r["primary_return"]) for r in records]
    sessions = sorted({r["session_date"] for r in records})
    session_means = [statistics.fmean([float(r["primary_return"]) for r in records if r["session_date"] == s]) for s in sessions]
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in vals:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return {
        "candidate_count": len(records),
        "session_count": len(sessions),
        "mean_return": mean(vals),
        "median_return": median(vals),
        "positive_trade_fraction": round(sum(1 for v in vals if v > 0) / len(vals), 12) if vals else None,
        "positive_session_fraction": round(sum(1 for v in session_means if v > 0) / len(session_means), 12) if session_means else None,
        "maximum_cumulative_drawdown": round(max_dd, 12),
    }


def by_field(records: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        grouped[str(r[field])].append(r)
    return {key: summarize(value) for key, value in sorted(grouped.items())}


def session_contribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    contrib: dict[str, float] = defaultdict(float)
    for r in records:
        contrib[r["session_date"]] += float(r["primary_return"])
    denom = sum(abs(v) for v in contrib.values())
    ordered = sorted(contrib.items(), key=lambda item: abs(item[1]), reverse=True)
    return {
        "single_largest_session": ordered[0] if ordered else None,
        "single_session_concentration": round(abs(ordered[0][1]) / denom, 12) if ordered and denom else None,
        "top_five_sessions": ordered[:5],
        "top_five_session_concentration": round(sum(abs(v) for _, v in ordered[:5]) / denom, 12) if denom else None,
    }


def bootstrap_ci(records: list[dict[str, Any]], metric: str, seed: int, n: int = BOOTSTRAP_RESAMPLES) -> dict[str, Any]:
    by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_session[r["session_date"]].append(r)
    sessions = sorted(by_session)
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(n):
        sample_records = []
        for _ in sessions:
            sample_records.extend(by_session[rng.choice(sessions)])
        if metric == "mean":
            value = mean([float(r["primary_return"]) for r in sample_records])
        elif metric == "top_mean":
            value = mean([float(r["primary_return"]) for r in sample_records if r.get("bucket") == "top"])
        elif metric == "spread":
            top = [float(r["primary_return"]) for r in sample_records if r.get("bucket") == "top"]
            bottom = [float(r["primary_return"]) for r in sample_records if r.get("bucket") == "bottom"]
            value = None if not top or not bottom else statistics.fmean(top) - statistics.fmean(bottom)
        elif metric == "spearman":
            value = spearman(sample_records)
        else:
            raise ValueError(metric)
        if value is not None:
            values.append(float(value))
    values.sort()
    return {
        "seed": seed,
        "resamples": n,
        "method": "session_cluster",
        "metric": metric,
        "lower": round(percentile(values, 0.025), 12) if values else None,
        "upper": round(percentile(values, 0.975), 12) if values else None,
        "sample_count": len(values),
    }


def score_thresholds(records: list[dict[str, Any]]) -> tuple[float, float]:
    scores = [float(r["score"]) for r in records]
    return percentile(scores, 0.2), percentile(scores, 0.8)


def mark_buckets(records: list[dict[str, Any]], low: float, high: float) -> list[dict[str, Any]]:
    out = []
    for r in records:
        item = dict(r)
        item["bucket"] = "top" if r["score"] >= high else "bottom" if r["score"] <= low else "middle"
        out.append(item)
    return out


def fold_plan(groups: dict[str, list[dict[str, Any]]]) -> tuple[list[str], list[str], list[list[str]]]:
    sessions = sorted(groups)
    dev_count = math.floor(len(sessions) * 0.8)
    dev = sessions[:dev_count]
    holdout = sessions[dev_count:]
    return dev, holdout, split_blocks(dev, 6)


def evaluate() -> dict[str, Any]:
    input_audit = audit_inputs()
    contract = build_contract(input_audit)
    groups = read_joined()
    dev_sessions, holdout_sessions, blocks = fold_plan(groups)
    folds = []
    aggregate_oos: list[dict[str, Any]] = []
    aggregate_oos_bucketed: list[dict[str, Any]] = []
    for i in range(1, 6):
        train_sessions = [s for block in blocks[:i] for s in block]
        val_sessions = blocks[i]
        train = flatten(groups, train_sessions)
        val = flatten(groups, val_sessions)
        low, high = score_thresholds(train)
        bucketed = mark_buckets(val, low, high)
        aggregate_oos.extend(val)
        aggregate_oos_bucketed.extend(bucketed)
        folds.append(
            {
                "fold": i,
                "train_session_count": len(train_sessions),
                "validation_session_count": len(val_sessions),
                "train_range": [train_sessions[0], train_sessions[-1]],
                "validation_range": [val_sessions[0], val_sessions[-1]],
                "training_score_20th_percentile": round(low, 12),
                "training_score_80th_percentile": round(high, 12),
                "all_candidate": summarize(val),
                "top_bucket": summarize([r for r in bucketed if r["bucket"] == "top"]),
                "bottom_bucket": summarize([r for r in bucketed if r["bucket"] == "bottom"]),
                "top_minus_bottom_spread": spread(bucketed),
                "spearman_score_outcome": spearman(val),
            }
        )
    full_dev = flatten(groups, dev_sessions)
    holdout = flatten(groups, holdout_sessions)
    holdout_low, holdout_high = score_thresholds(full_dev)
    holdout_bucketed = mark_buckets(holdout, holdout_low, holdout_high)
    combined_bucketed = aggregate_oos_bucketed + holdout_bucketed
    return {
        "input_audit": input_audit,
        "contract": contract,
        "folds": folds,
        "aggregate_oos": aggregate_oos,
        "aggregate_oos_bucketed": aggregate_oos_bucketed,
        "holdout": holdout,
        "holdout_bucketed": holdout_bucketed,
        "combined_bucketed": combined_bucketed,
        "holdout_thresholds": {
            "development_score_20th_percentile": round(holdout_low, 12),
            "development_score_80th_percentile": round(holdout_high, 12),
            "threshold_source": "full_development_only",
        },
    }


def spread(records: list[dict[str, Any]]) -> float | None:
    top = [float(r["primary_return"]) for r in records if r.get("bucket") == "top"]
    bottom = [float(r["primary_return"]) for r in records if r.get("bucket") == "bottom"]
    if not top or not bottom:
        return None
    return round(statistics.fmean(top) - statistics.fmean(bottom), 12)


def negative_controls(bucketed: list[dict[str, Any]]) -> dict[str, Any]:
    rng = random.Random(CONTROL_SEED)
    observed = spread(bucketed)
    sessions = sorted({r["session_date"] for r in bucketed})
    null_values = []
    for _ in range(CONTROL_PERMUTATIONS):
        permuted = []
        for session in sessions:
            rows = [r for r in bucketed if r["session_date"] == session]
            scores = [r["score"] for r in rows]
            rng.shuffle(scores)
            low, high = score_thresholds([dict(r, score=s) for r, s in zip(rows, scores)])
            permuted.extend(mark_buckets([dict(r, score=s) for r, s in zip(rows, scores)], low, high))
        value = spread(permuted)
        if value is not None:
            null_values.append(value)
    random_rows = [dict(r, score=random.Random(f"{CONTROL_SEED}:{r['candidate_id']}").random()) for r in bucketed]
    random_low, random_high = score_thresholds(random_rows)
    random_bucketed = mark_buckets(random_rows, random_low, random_high)
    inverted = [dict(r, score=-float(r["score"])) for r in bucketed]
    inv_low, inv_high = score_thresholds(inverted)
    inverted_bucketed = mark_buckets(inverted, inv_low, inv_high)
    percentile_rank = sum(1 for value in null_values if value <= (observed or 0.0)) / len(null_values)
    return {
        "seed": CONTROL_SEED,
        "permutations": CONTROL_PERMUTATIONS,
        "observed_top_minus_bottom_spread": observed,
        "within_session_permutation_null": {
            "p50": round(percentile(null_values, 0.5), 12),
            "p95": round(percentile(null_values, 0.95), 12),
            "observed_percentile_within_null": round(percentile_rank, 12),
        },
        "random_ranking_result": {"top_minus_bottom_spread": spread(random_bucketed)},
        "inverted_score_result": {"top_minus_bottom_spread": spread(inverted_bucketed)},
        "join_corruption_control": "PASS_FAILS_CLOSED",
        "future_suffix_mutation": "NOT_EVALUATED_RAW_CAUSAL_SOURCE_UNAVAILABLE",
        **safety(),
    }


def verdict(metrics: dict[str, Any]) -> str:
    all_oos = metrics["all_candidate_results"]["aggregate_development_oos"]
    holdout = metrics["final_holdout_results"]["all_candidate"]
    top_oos = metrics["score_discrimination_results"]["aggregate_development_oos"]["top_bucket"]
    top_holdout = metrics["score_discrimination_results"]["final_holdout"]["top_bucket"]
    spread_oos = metrics["score_discrimination_results"]["aggregate_development_oos"]["top_minus_bottom_spread"]
    uncertainty = metrics["statistical_uncertainty"]
    concentration = metrics["concentration_analysis"]
    controls = metrics["negative_controls"]
    fold_positive_all = sum(1 for f in metrics["wfa_fold_results"]["folds"] if (f["all_candidate"]["mean_return"] or 0) > 0)
    fold_positive_top = sum(1 for f in metrics["wfa_fold_results"]["folds"] if (f["top_bucket"]["mean_return"] or 0) > 0)
    sample_ok = metrics["sample_gates"]["decision"] == "PASS"
    conc_ok = (concentration["single_session_concentration"] or 1) <= 0.2
    all_gate = (
        sample_ok
        and (all_oos["mean_return"] or 0) > 0
        and fold_positive_all >= 4
        and (holdout["mean_return"] or 0) > 0
        and (uncertainty["aggregate_oos_mean"]["lower"] or -1) > 0
        and (uncertainty["final_holdout_mean"]["lower"] or -1) > 0
        and conc_ok
    )
    score_gate = (
        sample_ok
        and (top_oos["mean_return"] or 0) > 0
        and fold_positive_top >= 4
        and (top_holdout["mean_return"] or 0) > 0
        and (uncertainty["aggregate_oos_top_mean"]["lower"] or -1) > 0
        and (uncertainty["final_holdout_top_mean"]["lower"] or -1) > 0
        and (spread_oos or 0) > 0
        and (uncertainty["aggregate_oos_spread"]["lower"] or -1) > 0
        and controls["within_session_permutation_null"]["observed_percentile_within_null"] >= 0.95
        and conc_ok
    )
    if all_gate and not score_gate:
        return "CANDIDATE_EDGE_PRESENT_SCORE_NOT_PREDICTIVE"
    if all_gate:
        return "UNDERLYING_STRUCTURAL_EDGE_CONFIRMED"
    if score_gate:
        return "CORRECTED_SCORE_DISCRIMINATION_CONFIRMED"
    if (all_oos["mean_return"] or 0) <= 0 and (spread_oos or 0) <= 0:
        return "NO_UNDERLYING_STRUCTURAL_EDGE"
    return "UNDERLYING_SIGNAL_WEAK_OR_UNSTABLE"


def build_metrics() -> dict[str, Any]:
    ev = evaluate()
    aggregate_oos = ev["aggregate_oos"]
    aggregate_bucketed = ev["aggregate_oos_bucketed"]
    holdout = ev["holdout"]
    holdout_bucketed = ev["holdout_bucketed"]
    combined = ev["combined_bucketed"]
    top_oos = [r for r in aggregate_bucketed if r["bucket"] == "top"]
    bottom_oos = [r for r in aggregate_bucketed if r["bucket"] == "bottom"]
    top_holdout = [r for r in holdout_bucketed if r["bucket"] == "top"]
    bottom_holdout = [r for r in holdout_bucketed if r["bucket"] == "bottom"]
    sample_gates = {
        "eligible_candidates": len(aggregate_oos) + len(holdout),
        "sessions": len({r["session_date"] for r in aggregate_oos + holdout}),
        "aggregate_oos_top_bucket_candidates": len(top_oos),
        "aggregate_oos_bottom_bucket_candidates": len(bottom_oos),
        "call_count": sum(1 for r in aggregate_oos + holdout if r["direction"] == "BUY_CALL"),
        "put_count": sum(1 for r in aggregate_oos + holdout if r["direction"] == "BUY_PUT"),
    }
    concentration = session_contribution(aggregate_oos + holdout)
    sample_gates["single_session_concentration"] = concentration["single_session_concentration"]
    sample_gates["decision"] = (
        "PASS"
        if sample_gates["eligible_candidates"] >= 300
        and sample_gates["sessions"] >= 50
        and sample_gates["aggregate_oos_top_bucket_candidates"] >= 100
        and sample_gates["aggregate_oos_bottom_bucket_candidates"] >= 100
        and sample_gates["call_count"] > 0
        and sample_gates["put_count"] > 0
        and (sample_gates["single_session_concentration"] or 1) <= 0.2
        else "FAIL"
    )
    metrics: dict[str, Any] = {
        "source_identity": source_identity(),
        "input_audit": ev["input_audit"],
        "underlying_edge_contract": ev["contract"],
        "wfa_fold_results": {"folds": ev["folds"], **safety()},
        "all_candidate_results": {
            "aggregate_development_oos": summarize(aggregate_oos),
            "combined_oos_descriptive": summarize(aggregate_oos + holdout),
            "call_results": by_field(aggregate_oos + holdout, "direction").get("BUY_CALL"),
            "put_results": by_field(aggregate_oos + holdout, "direction").get("BUY_PUT"),
            "symbol_results": by_field(aggregate_oos + holdout, "symbol"),
            **safety(),
        },
        "final_holdout_results": {
            "all_candidate": summarize(holdout),
            "top_bucket": summarize(top_holdout),
            "bottom_bucket": summarize(bottom_holdout),
            "top_minus_bottom_spread": spread(holdout_bucketed),
            "spearman_score_outcome": spearman(holdout),
            "score_thresholds": ev["holdout_thresholds"],
            **safety(),
        },
        "score_discrimination_results": {
            "score_summary": {
                "minimum": min(r["score"] for r in aggregate_oos + holdout),
                "maximum": max(r["score"] for r in aggregate_oos + holdout),
                "mean": mean([r["score"] for r in aggregate_oos + holdout]),
                "median": median([r["score"] for r in aggregate_oos + holdout]),
            },
            "aggregate_development_oos": {
                "top_bucket": summarize(top_oos),
                "bottom_bucket": summarize(bottom_oos),
                "top_minus_bottom_spread": spread(aggregate_bucketed),
                "spearman_score_outcome": spearman(aggregate_oos),
            },
            "final_holdout": {
                "top_bucket": summarize(top_holdout),
                "bottom_bucket": summarize(bottom_holdout),
                "top_minus_bottom_spread": spread(holdout_bucketed),
                "spearman_score_outcome": spearman(holdout),
            },
            "call_score_calibration": by_field([r for r in combined if r["bucket"] != "middle"], "direction").get("BUY_CALL"),
            "put_score_calibration": by_field([r for r in combined if r["bucket"] != "middle"], "direction").get("BUY_PUT"),
            "symbol_score_calibration": by_field([r for r in combined if r["bucket"] != "middle"], "symbol"),
            **safety(),
        },
        "concentration_analysis": {
            **concentration,
            "by_direction": contribution_by(aggregate_oos + holdout, "direction"),
            "by_symbol": contribution_by(aggregate_oos + holdout, "symbol"),
            "by_month": contribution_by(aggregate_oos + holdout, "month"),
            "by_quarter": contribution_by(aggregate_oos + holdout, "quarter"),
            "by_weekday": contribution_by(aggregate_oos + holdout, "weekday"),
            **safety(),
        },
        "sample_gates": sample_gates,
    }
    uncertainty = {
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "aggregate_oos_mean": bootstrap_ci(aggregate_oos, "mean", BOOTSTRAP_SEED + 1),
        "final_holdout_mean": bootstrap_ci(holdout, "mean", BOOTSTRAP_SEED + 2),
        "aggregate_oos_top_mean": bootstrap_ci(aggregate_bucketed, "top_mean", BOOTSTRAP_SEED + 3),
        "final_holdout_top_mean": bootstrap_ci(holdout_bucketed, "top_mean", BOOTSTRAP_SEED + 4),
        "aggregate_oos_spread": bootstrap_ci(aggregate_bucketed, "spread", BOOTSTRAP_SEED + 5),
        "final_holdout_spread": bootstrap_ci(holdout_bucketed, "spread", BOOTSTRAP_SEED + 6),
        "spearman_score_outcome": bootstrap_ci(aggregate_oos, "spearman", BOOTSTRAP_SEED + 7),
        "call_mean": bootstrap_ci([r for r in aggregate_oos + holdout if r["direction"] == "BUY_CALL"], "mean", BOOTSTRAP_SEED + 8),
        "put_mean": bootstrap_ci([r for r in aggregate_oos + holdout if r["direction"] == "BUY_PUT"], "mean", BOOTSTRAP_SEED + 9),
        **safety(),
    }
    metrics["statistical_uncertainty"] = uncertainty
    metrics["negative_controls"] = negative_controls(aggregate_bucketed)
    metrics["final_verdict"] = {
        "final_verdict": verdict(metrics),
        "candidate_universe": "current certified corrected candidate universe",
        "candidate_conservation": "NOT_EVALUATED_DUAL_REPLAY_UNAVAILABLE",
        "option_economic_edge": "NOT_EVALUATED_NO_BID_ASK",
        "option_profitability_claimed": "NO",
        "production_files_changed": "NO",
        "thresholds_changed": "NO",
        "parameters_tuned": "NO",
        "broker_api_called": "NO",
        "order_action": "NO",
        "new_pr_created": "NO",
        **safety(),
    }
    return metrics


def contribution_by(records: list[dict[str, Any]], field: str) -> dict[str, float]:
    values: dict[str, float] = defaultdict(float)
    for r in records:
        if field == "month":
            key = r["session_date"][:7]
        elif field == "quarter":
            month = int(r["session_date"][5:7])
            key = f"{r['session_date'][:4]}-Q{((month - 1) // 3) + 1}"
        elif field == "weekday":
            import datetime as _dt

            key = _dt.date.fromisoformat(r["session_date"]).strftime("%A")
        else:
            key = str(r[field])
        values[key] += float(r["primary_return"])
    return {k: round(v, 12) for k, v in sorted(values.items())}


def final_report(metrics: dict[str, Any]) -> str:
    verdict_text = metrics["final_verdict"]["final_verdict"]
    all_oos = metrics["all_candidate_results"]["aggregate_development_oos"]
    holdout = metrics["final_holdout_results"]["all_candidate"]
    score = metrics["score_discrimination_results"]["aggregate_development_oos"]
    return f"""# Corrected ORB Underlying Edge Evaluation

FINAL VERDICT: {verdict_text}

This is an underlying-index directional study for the current certified corrected candidate universe. It is not an option profitability or option executable economics study.

## Primary Results

- Primary horizon: 15-minute direction-normalized underlying return
- Aggregate development OOS all-candidate mean: {all_oos["mean_return"]}
- Final holdout all-candidate mean: {holdout["mean_return"]}
- Aggregate development OOS top-bucket mean: {score["top_bucket"]["mean_return"]}
- Aggregate development OOS bottom-bucket mean: {score["bottom_bucket"]["mean_return"]}
- Aggregate top-minus-bottom spread: {score["top_minus_bottom_spread"]}
- Option economic edge: NOT_EVALUATED_NO_BID_ASK

## Boundary

No strategy thresholds, ORB predicates, score weights, production files, broker paths, order paths, risk paths, or feed paths were changed.
"""


def artifact_hashes(output_dir: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(output_dir.glob("*.json")):
        if path.name in {"artifact_audit.json", "determinism_report.json"}:
            continue
        payload = read_json(path)
        hashes[path.name] = sha256_bytes(canonical_bytes(payload))
    return hashes


def generate(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    metrics = build_metrics()
    for name in [
        "source_identity",
        "input_audit",
        "underlying_edge_contract",
        "all_candidate_results",
        "score_discrimination_results",
        "wfa_fold_results",
        "final_holdout_results",
        "statistical_uncertainty",
        "negative_controls",
        "concentration_analysis",
        "final_verdict",
    ]:
        write_json(output_dir / f"{name}.json", metrics[name])
    write_md(output_dir / "input_audit.md", f"# Input Audit\n\nDecision: {metrics['input_audit']['decision']}\n")
    write_md(output_dir / "final_report.md", final_report(metrics))
    hashes = artifact_hashes(output_dir)
    determinism = {
        "decision": "PENDING_EXTERNAL_TWO_RUN_COMPARISON",
        "semantic_hash": sha256_bytes(canonical_bytes(hashes)),
        "artifact_hashes": hashes,
        **safety(),
    }
    write_json(output_dir / "determinism_report.json", determinism)
    return metrics


def compare_runs(run_a: Path, run_b: Path) -> dict[str, Any]:
    a = artifact_hashes(run_a)
    b = artifact_hashes(run_b)
    differing = sorted(set(a) ^ set(b)) + [k for k in sorted(set(a) & set(b)) if a[k] != b[k]]
    return {
        "decision": "PASS" if not differing else "FAIL",
        "run_a_semantic_hash": sha256_bytes(canonical_bytes(a)),
        "run_b_semantic_hash": sha256_bytes(canonical_bytes(b)),
        "differing_artifacts": differing,
        "differing_json_paths": [],
        "run_a": str(run_a),
        "run_b": str(run_b),
        **safety(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    result = generate(args.output_dir)
    print(result["final_verdict"]["final_verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
