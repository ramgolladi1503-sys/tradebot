from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from research.opening_range_retest_edge_screen_v1 import contract as C

RETURN_FIELD = "directional_underlying_return"
TIMESTAMP = "2026-07-20T00:00:00Z"


def cbytes(payload: Any) -> bytes:
    return C.canonical_json_bytes(payload)


def shab(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def shafile(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    digest = shafile(path)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    digest = shafile(path)
    path.with_suffix(path.suffix + ".sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return digest


def safety() -> dict[str, Any]:
    return C.safety_fields()


def evidence_header(mode: str, decision: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": C.SCHEMA_VERSION,
        "mode": mode,
        "candidate_id": "ALL_ORB_OUTCOME_V2_CANDIDATES",
        "decision": decision,
        "reason": reason,
        "source": "opening_range_retest_outcome_ledger_v2.json",
        "timestamp": TIMESTAMP,
        **safety(),
    }


def verify_sidecar(path: Path) -> dict[str, Any]:
    actual = shafile(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    expected = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.exists() else None
    return {"path": path.name, "artifact_sha256": actual, "sidecar_sha256": expected, "sidecar_match": actual == expected}


def verify_source_authority(artifact_dir: Path) -> dict[str, Any]:
    ledger_path = artifact_dir / "opening_range_retest_outcome_ledger_v2.json"
    contract_path = artifact_dir / "opening_range_retest_outcome_contract_v2.json"
    overlap_path = artifact_dir / "opening_range_retest_outcome_overlap_v2.json"
    ledger = load_json(ledger_path)
    failures: list[str] = []
    sidecars = {
        "outcome_ledger": verify_sidecar(ledger_path),
        "outcome_contract": verify_sidecar(contract_path),
        "outcome_overlap": verify_sidecar(overlap_path),
    }
    for key, item in sidecars.items():
        if not item["sidecar_match"]:
            failures.append(f"SIDECAR_MISMATCH:{key}")
    if sidecars["outcome_ledger"]["artifact_sha256"] != C.SOURCE_LEDGER_SHA256:
        failures.append("SOURCE_LEDGER_SHA_MISMATCH")
    if sidecars["outcome_overlap"]["artifact_sha256"] != C.SOURCE_OVERLAP_SHA256:
        failures.append("SOURCE_OVERLAP_SHA_MISMATCH")
    if ledger.get("outcome_ledger_hash") != C.SOURCE_LEDGER_SEMANTIC_HASH:
        failures.append("SOURCE_LEDGER_SEMANTIC_HASH_MISMATCH")
    if sidecars["outcome_contract"]["artifact_sha256"] != C.OUTCOME_CONTRACT_SHA256:
        failures.append("OUTCOME_CONTRACT_SHA_MISMATCH")
    expected = {
        "frozen_code_sha": C.FROZEN_OUTCOME_CODE_SHA,
        "implementation_tree_hash": C.FROZEN_IMPLEMENTATION_TREE_HASH,
        "candidate_count": C.CERTIFIED_CANDIDATES,
        "join_verified_count": C.CERTIFIED_SOURCE_JOINS,
    }
    for key, value in expected.items():
        if ledger.get(key) != value:
            failures.append(f"LEDGER_FIELD_MISMATCH:{key}")
    records = ledger.get("records", [])
    ids = [record.get("candidate_id") for record in records]
    if len(records) != C.CERTIFIED_CANDIDATES:
        failures.append("LEDGER_RECORD_COUNT_MISMATCH")
    if len(ids) != len(set(ids)):
        failures.append("LEDGER_DUPLICATE_CANDIDATE_IDS")
    for horizon, count in C.EXPECTED_MEASURED_COUNTS.items():
        measured = sum(1 for record in records if record.get("horizons", {}).get(str(horizon), {}).get("status") == "MEASURED")
        if measured != count:
            failures.append(f"MEASURED_COUNT_MISMATCH:{horizon}:{measured}")
    return {
        "ledger": ledger,
        "source_authority": {
            "failures": failures,
            "sidecars": sidecars,
            "source_ledger_sha256": sidecars["outcome_ledger"]["artifact_sha256"],
            "source_ledger_semantic_hash": ledger.get("outcome_ledger_hash"),
            **safety(),
        },
    }


def parse_ts(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Asia/Kolkata").tz_localize(None)
    return ts


def entry_bucket(ts: pd.Timestamp) -> str:
    value = ts.strftime("%H:%M")
    for start, end in C.ENTRY_TIME_BUCKETS:
        if start <= value < end or (end == "15:29" and start <= value <= end):
            return f"{start}-{end}"
    return "OUT_OF_BUCKET"


def entry_bucket_30(ts: pd.Timestamp) -> str:
    start = pd.Timestamp(ts.date()) + pd.Timedelta(hours=9, minutes=15)
    end = pd.Timestamp(ts.date()) + pd.Timedelta(hours=15, minutes=30)
    if ts < start or ts >= end:
        return "OUT_OF_BUCKET"
    offset = int((ts - start).total_seconds() // 60)
    bucket_start = start + pd.Timedelta(minutes=(offset // 30) * 30)
    bucket_end = min(bucket_start + pd.Timedelta(minutes=30), end)
    return f"{bucket_start.strftime('%H:%M')}-{bucket_end.strftime('%H:%M')}"


def measured_rows(ledger: dict[str, Any], horizon: int) -> list[dict[str, Any]]:
    rows = []
    for record in ledger["records"]:
        h = record.get("horizons", {}).get(str(horizon), {})
        if h.get("status") != "MEASURED":
            continue
        core = record["candidate_core"]
        entry_start = parse_ts(record["legal_entry"]["start"])
        session = str(core["session_date"])
        symbol = str(core["symbol"])
        direction = str(core["direction"])
        ret = float(h[RETURN_FIELD])
        entry_open = float(record["legal_entry"]["open"])
        terminal_close = float(h["terminal_close"])
        mfe = float(h.get("mfe", 0.0))
        mae = float(h.get("mae", 0.0))
        rows.append(
            {
                "candidate_id": record["candidate_id"],
                "session_date": session,
                "year": int(session[:4]),
                "symbol": symbol,
                "direction": direction,
                "entry_start": entry_start,
                "entry_time": entry_start.strftime("%H:%M"),
                "entry_bucket": entry_bucket(entry_start),
                "entry_bucket_30": entry_bucket_30(entry_start),
                "proposal_ready_at": parse_ts(core["proposal_ready_at_iso"]),
                "entry_open": entry_open,
                "terminal_close": terminal_close,
                "terminal_start": parse_ts(h["terminal_start"]),
                "return": ret,
                "return_bps": ret * 10000.0,
                "unsigned_return": float(h.get("unsigned_underlying_return", abs(ret))),
                "mfe": mfe,
                "mae": mae,
                "mfe_bps": mfe * 10000.0,
                "mae_bps": mae * 10000.0,
                "source_logical_path": record["source_manifest_record"]["logical_path"],
            }
        )
    return rows


def mean(values: Iterable[float]) -> float:
    vals = list(values)
    return float(np.mean(vals)) if vals else 0.0


def median(values: Iterable[float]) -> float:
    vals = list(values)
    return float(np.median(vals)) if vals else 0.0


def trimmed_mean(values: Iterable[float], pct: float = 0.10) -> float:
    vals = sorted(values)
    if not vals:
        return 0.0
    cut = int(len(vals) * pct)
    kept = vals[cut : len(vals) - cut] if len(vals) - cut > cut else vals
    return float(np.mean(kept))


def session_means(rows: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row["session_date"]].append(row["return"])
    return {key: mean(vals) for key, vals in sorted(grouped.items())}


def symbol_session_means(rows: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row["symbol"], row["session_date"])].append(row["return"])
    return {f"{symbol}:{session}": mean(vals) for (symbol, session), vals in sorted(grouped.items())}


def bootstrap(values: list[float], seed: int = C.BOOTSTRAP_SEED, reps: int = C.BOOTSTRAP_REPLICATIONS) -> dict[str, Any]:
    arr = np.array(values, dtype=float)
    if len(arr) == 0:
        empty_hash = shab(cbytes([]))
        return {
            "replications": reps,
            "seed": seed,
            "lower": 0.0,
            "upper": 0.0,
            "lower_bps": 0.0,
            "upper_bps": 0.0,
            "bootstrap_mean": 0.0,
            "bootstrap_mean_bps": 0.0,
            "distribution_hash": empty_hash,
            "p_le_zero": 1.0,
            "p_gt_zero": 0.0,
            "p_ge_1bp": 0.0,
            "mcse_p_gt_zero": 0.0,
            "mcse_p_ge_1bp": 0.0,
        }
    rng = np.random.default_rng(seed)
    stats = np.empty(reps, dtype=float)
    n = len(arr)
    for i in range(reps):
        stats[i] = float(np.mean(arr[rng.integers(0, n, n)]))
    p_gt_zero = float(np.mean(stats > 0.0))
    p_ge_1bp = float(np.mean(stats >= 0.0001))
    return {
        "replications": reps,
        "seed": seed,
        "lower": float(np.percentile(stats, 2.5)),
        "upper": float(np.percentile(stats, 97.5)),
        "lower_bps": float(np.percentile(stats, 2.5) * 10000.0),
        "upper_bps": float(np.percentile(stats, 97.5) * 10000.0),
        "bootstrap_mean": float(np.mean(stats)),
        "bootstrap_mean_bps": float(np.mean(stats) * 10000.0),
        "distribution_hash": shab(cbytes([round(float(value), 15) for value in stats])),
        "p_le_zero": float(np.mean(stats <= 0.0)),
        "p_gt_zero": p_gt_zero,
        "p_ge_1bp": p_ge_1bp,
        "mcse_p_gt_zero": math.sqrt(p_gt_zero * (1.0 - p_gt_zero) / reps),
        "mcse_p_ge_1bp": math.sqrt(p_ge_1bp * (1.0 - p_ge_1bp) / reps),
    }


def sign_test_positive(values: list[float]) -> dict[str, Any]:
    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)
    n = pos + neg
    if n == 0:
        one_sided = 1.0
        two_sided = 1.0
    else:
        one_sided = sum(math.comb(n, i) for i in range(pos, n + 1)) / (2**n)
        k = min(pos, neg)
        two_sided = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2**n))
    return {
        "positive": pos,
        "negative": neg,
        "zero": len(values) - n,
        "binomial_n_excluding_zero": n,
        "one_sided_p_positive_tendency": one_sided,
        "two_sided_p": two_sided,
    }


def distribution_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": 0.0, "median": 0.0, "std": 0.0, "se": 0.0, "min": 0.0, "p25": 0.0, "p75": 0.0, "max": 0.0}
    arr = np.array(values, dtype=float)
    return {
        "count": len(values),
        "mean": float(np.mean(arr)),
        "mean_bps": float(np.mean(arr) * 10000.0),
        "median": float(np.median(arr)),
        "median_bps": float(np.median(arr) * 10000.0),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "std_bps": float(np.std(arr, ddof=1) * 10000.0) if len(arr) > 1 else 0.0,
        "se": float(np.std(arr, ddof=1) / math.sqrt(len(arr))) if len(arr) > 1 else 0.0,
        "se_bps": float(np.std(arr, ddof=1) * 10000.0 / math.sqrt(len(arr))) if len(arr) > 1 else 0.0,
        "min": float(np.min(arr)),
        "min_bps": float(np.min(arr) * 10000.0),
        "p25": float(np.percentile(arr, 25)),
        "p25_bps": float(np.percentile(arr, 25) * 10000.0),
        "p75": float(np.percentile(arr, 75)),
        "p75_bps": float(np.percentile(arr, 75) * 10000.0),
        "max": float(np.max(arr)),
        "max_bps": float(np.max(arr) * 10000.0),
    }


def descriptive_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    returns = [row["return"] for row in rows]
    session_values = list(session_means(rows).values())
    symbol_session_values = list(symbol_session_means(rows).values())
    pos = sum(1 for value in returns if value > 0)
    neg = sum(1 for value in returns if value < 0)
    zero = len(returns) - pos - neg
    mfe_values = [row["mfe"] for row in rows]
    mae_values = [row["mae"] for row in rows]
    mae_abs = abs(mean(mae_values))
    return {
        "candidate_count": len(rows),
        "session_count": len(session_values),
        "candidate_mean": mean(returns),
        "candidate_mean_bps": mean(returns) * 10000.0,
        "session_equal_mean": mean(session_values),
        "session_equal_mean_bps": mean(session_values) * 10000.0,
        "symbol_session_equal_mean": mean(symbol_session_values),
        "symbol_session_equal_mean_bps": mean(symbol_session_values) * 10000.0,
        "median": median(returns),
        "median_bps": median(returns) * 10000.0,
        "trimmed_mean": trimmed_mean(returns),
        "trimmed_mean_bps": trimmed_mean(returns) * 10000.0,
        "std": float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0,
        "p05": float(np.percentile(returns, 5)) if returns else 0.0,
        "p25": float(np.percentile(returns, 25)) if returns else 0.0,
        "p75": float(np.percentile(returns, 75)) if returns else 0.0,
        "p95": float(np.percentile(returns, 95)) if returns else 0.0,
        "positive_count": pos,
        "zero_count": zero,
        "negative_count": neg,
        "positive_rate": pos / len(returns) if returns else 0.0,
        "mean_mfe": mean(mfe_values),
        "median_mfe": median(mfe_values),
        "mean_mae": mean(mae_values),
        "median_mae": median(mae_values),
        "mfe_abs_mae_ratio": mean(mfe_values) / mae_abs if mae_abs else None,
        "session_distribution": distribution_summary(session_values),
        "candidates_per_session_distribution": distribution_summary([float(v) for v in pd.Series([row["session_date"] for row in rows]).value_counts().to_list()]) if rows else distribution_summary([]),
        "sign_test": sign_test_positive(session_values),
    }


def metrics_payload(ledger: dict[str, Any]) -> dict[str, Any]:
    horizons: dict[str, Any] = {}
    for horizon in C.HORIZONS:
        rows = measured_rows(ledger, horizon)
        stats = descriptive_stats(rows)
        sessions = list(session_means(rows).values())
        stats["session_cluster_bootstrap"] = bootstrap(sessions)
        stats["sign_test"] = sign_test_positive(sessions)
        stats["hurdles"] = {f"{hurdle}_bps": stats["session_equal_mean_bps"] - hurdle for hurdle in C.PRACTICAL_HURDLES_BPS}
        horizons[str(horizon)] = stats

    rows15 = measured_rows(ledger, C.PRIMARY_HORIZON)
    symbol_direction = {}
    raw_p = []
    for symbol, direction in C.SYMBOL_DIRECTION_CELLS:
        subset = [row for row in rows15 if row["symbol"] == symbol and row["direction"] == direction]
        stats = descriptive_stats(subset)
        boot = bootstrap(list(session_means(subset).values()), seed=C.BOOTSTRAP_SEED + len(raw_p) + 1)
        stats["session_cluster_bootstrap"] = boot
        stats["sign_test"] = sign_test_positive(list(session_means(subset).values()))
        stats["one_sided_p"] = stats["sign_test"]["one_sided_p_positive_tendency"]
        key = f"{symbol}:{direction}"
        raw_p.append((key, stats["one_sided_p"]))
        symbol_direction[key] = stats
    sorted_p = sorted(raw_p, key=lambda item: item[1])
    holm: dict[str, Any] = {}
    running = 0.0
    m = len(sorted_p)
    for rank, (key, pvalue) in enumerate(sorted_p, start=1):
        adjusted = min(1.0, max(running, (m - rank + 1) * pvalue))
        running = adjusted
        holm[key] = {"raw_p": pvalue, "holm_adjusted_p": adjusted, "reject_0_05": adjusted <= C.HOLM_ALPHA}
    for key, item in symbol_direction.items():
        item["holm"] = holm[key]

    payload = {
        **evidence_header("ORB_EDGE_SCREEN_METRICS_V1", "ORB_EDGE_SCREEN_METRICS_RECOMPUTED", "recomputed fixed horizon metrics from certified outcome ledger records"),
        "horizons": horizons,
        "primary_horizon": C.PRIMARY_HORIZON,
        "secondary_horizon": C.SECONDARY_HORIZON,
        "primary": horizons[str(C.PRIMARY_HORIZON)],
        "secondary": horizons[str(C.SECONDARY_HORIZON)],
        "symbol_direction": symbol_direction,
        "projection_hash": shab(cbytes({"horizons": horizons, "symbol_direction": symbol_direction})),
    }
    return payload


def random_direction_control(rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed = mean(session_means(rows).values())
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["symbol"], row["year"])].append(row)
    rng = random.Random(C.RANDOM_DIRECTION_SEED)
    diffs = []
    control_stats = []
    for _ in range(C.RANDOM_DIRECTION_PERMUTATIONS):
        permuted = []
        for group_rows in groups.values():
            directions = [row["direction"] for row in group_rows]
            rng.shuffle(directions)
            for row, direction in zip(group_rows, directions):
                sign = 1.0 if direction == "BUY_CALL" else -1.0
                item = dict(row)
                item["return"] = sign * row["unsigned_return"]
                permuted.append(item)
        control_stat = mean(session_means(permuted).values())
        control_stats.append(control_stat)
        diffs.append(observed - control_stat)
    arr = np.array(diffs)
    count_control_ge_observed = sum(1 for value in control_stats if value >= observed)
    return {
        "observed_signal_session_equal_mean": observed,
        "observed_statistic": observed,
        "control_distribution_summary": distribution_summary(control_stats),
        "mean_advantage": float(np.mean(arr)),
        "mean_advantage_bps": float(np.mean(arr) * 10000.0),
        "lower": float(np.percentile(arr, 2.5)),
        "upper": float(np.percentile(arr, 97.5)),
        "lower_bps": float(np.percentile(arr, 2.5) * 10000.0),
        "upper_bps": float(np.percentile(arr, 97.5) * 10000.0),
        "count_control_ge_observed": count_control_ge_observed,
        "permutation_p": (1 + count_control_ge_observed) / (1 + C.RANDOM_DIRECTION_PERMUTATIONS),
        "p_value_formula": "(1 + count(control >= observed)) / (1 + permutations)",
        "permutations": C.RANDOM_DIRECTION_PERMUTATIONS,
        "seed": C.RANDOM_DIRECTION_SEED,
    }


def opposite_direction_control(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tolerance = 1e-10
    exact_matches = 0
    tolerance_matches = 0
    mismatches = 0
    max_abs_error = 0.0
    first_mismatch = None
    for row in rows:
        raw = (row["terminal_close"] - row["entry_open"]) / row["entry_open"]
        signal = raw if row["direction"] == "BUY_CALL" else -raw
        opposite = -raw if row["direction"] == "BUY_CALL" else raw
        error = abs(signal - row["return"])
        identity_error = abs(signal + opposite)
        total_error = max(error, identity_error)
        max_abs_error = max(max_abs_error, total_error)
        if total_error == 0.0:
            exact_matches += 1
        elif total_error <= tolerance:
            tolerance_matches += 1
        else:
            mismatches += 1
            if first_mismatch is None:
                first_mismatch = {
                    "candidate_id": row["candidate_id"],
                    "expected_signal": row["return"],
                    "recomputed_signal": signal,
                    "recomputed_opposite": opposite,
                    "signal_error": error,
                    "identity_error": identity_error,
                }
    return {
        "records_checked": len(rows),
        "exact_matches": exact_matches,
        "tolerance_matches": tolerance_matches,
        "mismatches": mismatches,
        "max_abs_error": max_abs_error,
        "first_mismatch": first_mismatch,
        "tolerance": tolerance,
        "verdict": "PASS" if mismatches == 0 else "FAIL",
    }


def source_path(logical: str, source_project_root: Path) -> Path:
    logical_path = Path(logical)
    if logical_path.is_absolute() or ".." in logical_path.parts:
        raise ValueError("SOURCE_PATH_TRAVERSAL")
    path = (source_project_root / logical_path).resolve()
    path.relative_to((source_project_root / "runtime" / "upstox_candidate_replay").resolve())
    return path


def read_source_frame(logical: str, source_project_root: Path, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if logical not in cache:
        frame = pd.read_parquet(source_path(logical, source_project_root)).copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
        if frame["timestamp"].dt.tz is not None:
            frame["timestamp"] = frame["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
        cache[logical] = frame
    return cache[logical]


def matched_time_control(rows: list[dict[str, Any]], source_project_root: Path, horizon: int = C.PRIMARY_HORIZON) -> dict[str, Any]:
    rng = random.Random(C.MATCHED_TIME_SEED)
    cache: dict[str, pd.DataFrame] = {}
    matched_rows = []
    candidate_diffs = []
    eligible_counts = []
    uncovered_ids = []
    shortage_count = 0
    replacement_sampling_count = 0
    covered = 0
    total_draws = 0
    for row in rows:
        frame = read_source_frame(row["source_logical_path"], source_project_root, cache)
        frame = frame.reset_index(drop=True)
        bucket = row["entry_bucket"]
        start_s, end_s = bucket.split("-")
        candidates = []
        for idx, bar in frame.iterrows():
            start = parse_ts(bar["timestamp"])
            time_text = start.strftime("%H:%M")
            if not (start_s <= time_text < end_s or (end_s == "15:29" and start_s <= time_text <= end_s)):
                continue
            if start == row["entry_start"]:
                continue
            terminal_ts = start + pd.Timedelta(minutes=horizon)
            terminal = frame[frame["timestamp"] == terminal_ts]
            if terminal.empty:
                continue
            candidates.append((float(bar["open"]), float(terminal.iloc[0]["close"])))
        if not candidates:
            uncovered_ids.append(row["candidate_id"])
            continue
        eligible_counts.append(len(candidates))
        if len(candidates) < C.MATCHED_TIME_DRAWS_PER_CANDIDATE:
            shortage_count += 1
            replacement_sampling_count += 1
        covered += 1
        candidate_returns = []
        for _ in range(C.MATCHED_TIME_DRAWS_PER_CANDIDATE):
            entry_open, terminal_close = candidates[rng.randrange(len(candidates))]
            raw = (terminal_close - entry_open) / entry_open
            ret = raw if row["direction"] == "BUY_CALL" else -raw
            item = dict(row)
            item["return"] = ret
            matched_rows.append(item)
            candidate_returns.append(ret)
            total_draws += 1
        candidate_diffs.append(row["return"] - mean(candidate_returns))
    observed = mean(session_means(rows).values())
    matched = mean(session_means(matched_rows).values())
    # Bootstrap paired by session date over observed-minus-control session means.
    obs_sessions = session_means(rows)
    ctl_sessions = session_means(matched_rows)
    common = sorted(set(obs_sessions) & set(ctl_sessions))
    diffs = [obs_sessions[key] - ctl_sessions[key] for key in common]
    boot = bootstrap(diffs, seed=C.MATCHED_TIME_SEED)
    control_distribution = list(ctl_sessions.values())
    count_control_ge_observed = sum(1 for value in control_distribution if value >= observed)
    return {
        "coverage": covered / len(rows) if rows else 0.0,
        "covered_candidates": covered,
        "uncovered_candidates": len(rows) - covered,
        "uncovered_sample": sorted(uncovered_ids)[:10],
        "candidate_count": len(rows),
        "eligible_timestamp_count_distribution": distribution_summary([float(v) for v in eligible_counts]),
        "shortage_count": shortage_count,
        "replacement_sampling_count": replacement_sampling_count,
        "draws": total_draws,
        "draws_per_candidate": C.MATCHED_TIME_DRAWS_PER_CANDIDATE,
        "candidate_level_observed_minus_matched_mean": mean(candidate_diffs),
        "candidate_level_observed_minus_matched_mean_bps": mean(candidate_diffs) * 10000.0,
        "signal_session_equal_mean": observed,
        "matched_time_session_equal_mean": matched,
        "matched_control_distribution": distribution_summary(control_distribution),
        "count_control_ge_observed": count_control_ge_observed,
        "empirical_one_sided_add_one_p": (1 + count_control_ge_observed) / (1 + len(control_distribution)) if control_distribution else 1.0,
        "paired_session_bootstrap_ci": boot,
        "advantage": observed - matched,
        "advantage_bps": (observed - matched) * 10000.0,
        "advantage_ci": boot,
        "seed": C.MATCHED_TIME_SEED,
    }


def within_stratum_control(rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed = mean(session_means(rows).values())
    groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["symbol"], row["year"], row["entry_bucket_30"])].append(row)
    eligible_groups = {
        key: group_rows
        for key, group_rows in groups.items()
        if len(group_rows) >= 2 and {row["direction"] for row in group_rows} == set(C.DIRECTIONS)
    }
    eligible_ids = {row["candidate_id"] for group_rows in eligible_groups.values() for row in group_rows}
    eligible_rows = [row for row in rows if row["candidate_id"] in eligible_ids]
    eligible_coverage = len(eligible_rows) / len(rows) if rows else 0.0
    observed_eligible = mean(session_means(eligible_rows).values()) if eligible_rows else 0.0
    rng = random.Random(C.WITHIN_STRATUM_SEED)
    diffs = []
    control_stats = []
    for _ in range(C.WITHIN_STRATUM_PERMUTATIONS):
        permuted = []
        for group_rows in eligible_groups.values():
            directions = [row["direction"] for row in group_rows]
            rng.shuffle(directions)
            for row, direction in zip(group_rows, directions):
                sign = 1.0 if direction == "BUY_CALL" else -1.0
                item = dict(row)
                item["return"] = sign * row["unsigned_return"]
                permuted.append(item)
        control_stat = mean(session_means(permuted).values()) if permuted else 0.0
        control_stats.append(control_stat)
        diffs.append(observed_eligible - control_stat)
    arr = np.array(diffs)
    count_control_ge_observed = sum(1 for value in control_stats if value >= observed_eligible)
    return {
        "observed_signal_session_equal_mean": observed,
        "observed_eligible_session_equal_mean": observed_eligible,
        "observed_statistic": observed_eligible,
        "eligible_candidate_count": len(eligible_rows),
        "ineligible_candidate_count": len(rows) - len(eligible_rows),
        "eligible_stratum_count": len(eligible_groups),
        "ineligible_stratum_count": len(groups) - len(eligible_groups),
        "eligible_coverage": eligible_coverage,
        "coverage_verdict": "UNDERPOWERED" if eligible_coverage < 0.50 else "ADEQUATE",
        "control_distribution_summary": distribution_summary(control_stats),
        "mean_advantage": float(np.mean(arr)),
        "mean_advantage_bps": float(np.mean(arr) * 10000.0),
        "lower": float(np.percentile(arr, 2.5)),
        "upper": float(np.percentile(arr, 97.5)),
        "lower_bps": float(np.percentile(arr, 2.5) * 10000.0),
        "upper_bps": float(np.percentile(arr, 97.5) * 10000.0),
        "count_control_ge_observed": count_control_ge_observed,
        "permutation_p": (1 + count_control_ge_observed) / (1 + C.WITHIN_STRATUM_PERMUTATIONS),
        "p_value_formula": "(1 + count(control >= observed)) / (1 + permutations)",
        "permutations": C.WITHIN_STRATUM_PERMUTATIONS,
        "seed": C.WITHIN_STRATUM_SEED,
    }


def controls_payload(ledger: dict[str, Any], source_project_root: Path) -> dict[str, Any]:
    rows = measured_rows(ledger, C.PRIMARY_HORIZON)
    payload = {
        **evidence_header("ORB_EDGE_SCREEN_CONTROLS_V1", "ORB_EDGE_SCREEN_CONTROLS_RECOMPUTED", "recomputed random-direction, opposite-direction, matched-time, and within-stratum controls"),
        "random_direction": random_direction_control(rows),
        "opposite_direction": opposite_direction_control(rows),
        "matched_time": matched_time_control(rows, source_project_root),
        "within_stratum_direction_permutation": within_stratum_control(rows),
    }
    payload["projection_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "projection_hash"}))
    return payload


def concentration_payload(ledger: dict[str, Any]) -> dict[str, Any]:
    rows = measured_rows(ledger, C.PRIMARY_HORIZON)
    sessions = session_means(rows)
    total_positive = sum(v for v in sessions.values() if v > 0)
    best = sorted(sessions.items(), key=lambda item: item[1], reverse=True)
    worst = sorted(sessions.items(), key=lambda item: item[1])

    def remove_sessions(keys: set[str]) -> float:
        return mean(session_means([row for row in rows if row["session_date"] not in keys]).values())

    top_count = max(1, math.ceil(len(rows) * 0.01))
    top_ids = {row["candidate_id"] for row in sorted(rows, key=lambda item: item["return"], reverse=True)[:top_count]}
    without_top = [row for row in rows if row["candidate_id"] not in top_ids]
    by_year = {str(year): mean(session_means([row for row in rows if row["year"] == year]).values()) for year in C.YEARS}
    by_symbol = {symbol: mean(session_means([row for row in rows if row["symbol"] == symbol]).values()) for symbol in C.SYMBOLS}
    by_cell = {
        f"{symbol}:{direction}": mean(session_means([row for row in rows if row["symbol"] == symbol and row["direction"] == direction]).values())
        for symbol, direction in C.SYMBOL_DIRECTION_CELLS
    }
    most_positive_year = sorted(by_year.items(), key=lambda item: (-item[1], item[0]))[0][0]
    most_positive_symbol = sorted(by_symbol.items(), key=lambda item: (-item[1], item[0]))[0][0]
    most_positive_cell = sorted(by_cell.items(), key=lambda item: (-item[1], item[0]))[0][0]
    session_values = list(sessions.values())
    lo = float(np.percentile(session_values, 1)) if session_values else 0.0
    hi = float(np.percentile(session_values, 99)) if session_values else 0.0
    winsorized = [min(max(value, lo), hi) for value in session_values]
    payload = {
        **evidence_header("ORB_EDGE_SCREEN_CONCENTRATION_V1", "ORB_EDGE_SCREEN_CONCENTRATION_RECOMPUTED", "recomputed pre-registered concentration controls without return-based rescue selection"),
        "best_session_contribution": best[0][1] / total_positive if total_positive > 0 else None,
        "best_5_session_contribution": sum(v for _, v in best[:5] if v > 0) / total_positive if total_positive > 0 else None,
        "best_10_session_contribution": sum(v for _, v in best[:10] if v > 0) / total_positive if total_positive > 0 else None,
        "best_1pct_candidate_contribution": sum(row["return"] for row in rows if row["candidate_id"] in top_ids and row["return"] > 0) / sum(row["return"] for row in rows if row["return"] > 0) if sum(row["return"] for row in rows if row["return"] > 0) > 0 else None,
        "removal_means": {
            "best_1_session_removed": remove_sessions({k for k, _ in best[:1]}),
            "best_3_sessions_removed": remove_sessions({k for k, _ in best[:3]}),
            "best_5_sessions_removed": remove_sessions({k for k, _ in best[:5]}),
            "best_10_sessions_removed": remove_sessions({k for k, _ in best[:10]}),
            "top_1pct_candidates_removed": mean(session_means(without_top).values()),
            "worst_1_session_removed": remove_sessions({k for k, _ in worst[:1]}),
            "worst_5_sessions_removed": remove_sessions({k for k, _ in worst[:5]}),
            "most_positive_session_removed": remove_sessions({k for k, _ in best[:1]}),
            "five_most_positive_sessions_removed": remove_sessions({k for k, _ in best[:5]}),
            "most_positive_year_removed": mean(session_means([row for row in rows if row["year"] != int(most_positive_year)]).values()),
            "most_positive_symbol_removed": mean(session_means([row for row in rows if row["symbol"] != most_positive_symbol]).values()),
            "most_positive_symbol_direction_removed": mean(
                session_means([row for row in rows if f"{row['symbol']}:{row['direction']}" != most_positive_cell]).values()
            ),
            "session_mean_winsorized_1_99": mean(winsorized),
        },
        "selected_identities": {
            "most_positive_session": best[0][0],
            "five_most_positive_sessions": [key for key, _ in best[:5]],
            "most_positive_year": most_positive_year,
            "most_positive_symbol": most_positive_symbol,
            "most_positive_symbol_direction": most_positive_cell,
            "winsorize_session_mean_p01": lo,
            "winsorize_session_mean_p99": hi,
        },
        "top_1pct_candidate_count": top_count,
    }
    payload["projection_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "projection_hash"}))
    return payload


def replication_payload(ledger: dict[str, Any]) -> dict[str, Any]:
    rows = measured_rows(ledger, C.PRIMARY_HORIZON)
    sessions = session_means(rows)
    total_signed_abs = sum(abs(v) for v in sessions.values())

    def subgroup_stats(subset: list[dict[str, Any]]) -> dict[str, Any]:
        stats = descriptive_stats(subset)
        subgroup_sessions = list(session_means(subset).values())
        stats["session_cluster_bootstrap"] = bootstrap(subgroup_sessions)
        stats["sign_test"] = sign_test_positive(subgroup_sessions)
        stats["share_of_candidates"] = len(subset) / len(rows) if rows else 0.0
        signed = sum(session_means(subset).values())
        stats["share_of_aggregate_signed_contribution"] = signed / total_signed_abs if total_signed_abs else 0.0
        return stats

    by_year = {str(year): subgroup_stats([row for row in rows if row["year"] == year]) for year in C.YEARS}
    by_symbol = {symbol: subgroup_stats([row for row in rows if row["symbol"] == symbol]) for symbol in C.SYMBOLS}
    by_direction = {direction: subgroup_stats([row for row in rows if row["direction"] == direction]) for direction in C.DIRECTIONS}
    by_cell = {f"{symbol}:{direction}": subgroup_stats([row for row in rows if row["symbol"] == symbol and row["direction"] == direction]) for symbol, direction in C.SYMBOL_DIRECTION_CELLS}
    raw_p = sorted((key, item["sign_test"]["one_sided_p_positive_tendency"]) for key, item in by_cell.items())
    sorted_p = sorted(raw_p, key=lambda item: item[1])
    running = 0.0
    holm: dict[str, Any] = {}
    m = len(sorted_p)
    for rank, (key, pvalue) in enumerate(sorted_p, start=1):
        adjusted = min(1.0, max(running, (m - rank + 1) * pvalue))
        running = adjusted
        holm[key] = {"raw_p": pvalue, "holm_adjusted_p": adjusted, "reject_0_05": adjusted <= C.HOLM_ALPHA}
    for key, item in by_cell.items():
        item["holm"] = holm[key]
    payload = {
        **evidence_header("ORB_EDGE_SCREEN_REPLICATION_V1", "ORB_EDGE_SCREEN_REPLICATION_RECOMPUTED", "recomputed year, symbol, and direction replication tables from certified outcomes"),
        "years": by_year,
        "symbols": by_symbol,
        "directions": by_direction,
        "symbol_direction_cells": by_cell,
    }
    payload["projection_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "projection_hash"}))
    return payload


def overlap_components(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["session_date"], row["symbol"])].append(row)
    membership: dict[str, str] = {}
    components: dict[str, list[dict[str, Any]]] = {}
    for (session, symbol), group_rows in sorted(groups.items()):
        current: list[dict[str, Any]] = []
        current_end: pd.Timestamp | None = None
        index = 0
        for row in sorted(group_rows, key=lambda item: (item["entry_start"], item["terminal_start"], item["candidate_id"])):
            if not current or (current_end is not None and row["entry_start"] < current_end):
                current.append(row)
                current_end = row["terminal_start"] if current_end is None else max(current_end, row["terminal_start"])
                continue
            component_id = f"{session}:{symbol}:{index:04d}"
            components[component_id] = current
            for item in current:
                membership[item["candidate_id"]] = component_id
            index += 1
            current = [row]
            current_end = row["terminal_start"]
        if current:
            component_id = f"{session}:{symbol}:{index:04d}"
            components[component_id] = current
            for item in current:
                membership[item["candidate_id"]] = component_id
    return {"membership": membership, "components": components}


def overlap_payload(ledger: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    rows = measured_rows(ledger, C.PRIMARY_HORIZON)
    overlap_path = artifact_dir / "opening_range_retest_outcome_overlap_v2.json"
    overlap_authority = load_json(overlap_path)
    validation_failures = []
    authority_sha = shafile(overlap_path)
    if authority_sha != C.SOURCE_OVERLAP_SHA256:
        validation_failures.append("OVERLAP_AUTHORITY_SHA_MISMATCH")
    horizon_authority = overlap_authority.get("horizons", {}).get(str(C.PRIMARY_HORIZON), {})
    if horizon_authority.get("complete_interval_count") != len(rows):
        validation_failures.append("OVERLAP_AUTHORITY_INTERVAL_COUNT_MISMATCH")
    component_result = overlap_components(rows)
    membership = component_result["membership"]
    components = component_result["components"]
    if len(membership) != len(rows):
        validation_failures.append("OVERLAP_COMPONENT_ORPHAN_OR_DUPLICATE_MEMBERSHIP")
    grouped_symbol_session: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_symbol_session[(row["session_date"], row["symbol"])].append(row)
    one_per_component = [sorted(items, key=lambda row: (row["proposal_ready_at"], row["candidate_id"]))[0] for _, items in sorted(components.items())]
    earliest_symbol_session = [sorted(items, key=lambda row: (row["proposal_ready_at"], row["candidate_id"]))[0] for _, items in sorted(grouped_symbol_session.items())]
    payload = {
        **evidence_header("ORB_EDGE_SCREEN_OVERLAP_V1", "ORB_EDGE_SCREEN_OVERLAP_RECOMPUTED", "recomputed pre-registered non-return overlap sensitivities"),
        "authority": {
            "path": C.SOURCE_OVERLAP_PATH,
            "sha256": authority_sha,
            "expected_sha256": C.SOURCE_OVERLAP_SHA256,
            "complete_interval_count": horizon_authority.get("complete_interval_count"),
            "validation_failures": validation_failures,
        },
        "all_candidates": {"rule": "all measured 15-minute candidates", **descriptive_stats(rows)},
        "one_per_accepted_overlap_component": {
            "rule": "earliest proposal_ready_at then candidate_id per deterministic accepted interval component",
            "component_count": len(components),
            "membership_count": len(membership),
            **descriptive_stats(one_per_component),
        },
        "earliest_per_symbol_session": {
            "rule": "earliest proposal_ready_at then candidate_id per symbol-session",
            "symbol_session_count": len(grouped_symbol_session),
            **descriptive_stats(earliest_symbol_session),
        },
    }
    payload["projection_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "projection_hash"}))
    return payload


def structural_and_conditional(metrics: dict[str, Any], controls: dict[str, Any], concentration: dict[str, Any], replication: dict[str, Any], overlap: dict[str, Any]) -> dict[str, Any]:
    primary = metrics["primary"]
    rand = controls["random_direction"]
    matched = controls["matched_time"]
    within = controls["within_stratum_direction_permutation"]
    years = replication["years"]
    symbols = replication["symbols"]
    structural_gates = {
        "primary_15m_session_equal_mean_gt_0": primary["session_equal_mean"] > 0,
        "mean_ge_1bp": primary["session_equal_mean_bps"] >= C.STRUCTURAL_MIN_MEAN_BPS,
        "lower_ci_gt_0": primary["session_cluster_bootstrap"]["lower_bps"] > 0,
        "sign_test_one_sided_lte_0_05": primary["sign_test"]["one_sided_p_positive_tendency"] <= C.HOLM_ALPHA,
        "random_advantage_lower_ci_gt_0": rand["lower_bps"] > 0,
        "random_permutation_p_lte_0_05": rand["permutation_p"] <= 0.05,
        "matched_time_advantage_lower_ci_gt_0": matched["advantage_ci"]["lower_bps"] > 0,
        "matched_time_coverage_gte_95pct": matched["coverage"] >= C.MATCHED_TIME_MIN_COVERAGE,
        "within_stratum_coverage_not_underpowered": within["coverage_verdict"] != "UNDERPOWERED",
        "within_stratum_p_lte_0_05": within["permutation_p"] <= 0.05 and within["coverage_verdict"] != "UNDERPOWERED",
        "at_least_2_of_3_years_positive": sum(1 for item in years.values() if item["session_equal_mean"] > 0) >= 2,
        "no_year_below_minus_1bp": all(item["session_equal_mean_bps"] >= -1.0 for item in years.values()),
        "at_least_2_of_3_symbols_positive": sum(1 for item in symbols.values() if item["session_equal_mean"] > 0) >= 2,
        "best_5_concentration_lte_50pct": (concentration["best_5_session_contribution"] is not None and concentration["best_5_session_contribution"] <= 0.50),
        "positive_after_five_most_positive_sessions_removed": concentration["removal_means"]["five_most_positive_sessions_removed"] > 0,
        "positive_after_most_positive_year_removed": concentration["removal_means"]["most_positive_year_removed"] > 0,
        "positive_after_most_positive_symbol_removed": concentration["removal_means"]["most_positive_symbol_removed"] > 0,
        "positive_after_most_positive_symbol_direction_removed": concentration["removal_means"]["most_positive_symbol_direction_removed"] > 0,
        "positive_after_winsorized_session_means": concentration["removal_means"]["session_mean_winsorized_1_99"] > 0,
        "overlap_authority_valid": overlap["authority"]["validation_failures"] == [],
        "overlap_one_per_component_positive": overlap["one_per_accepted_overlap_component"]["session_equal_mean"] > 0,
        "overlap_earliest_symbol_session_positive": overlap["earliest_per_symbol_session"]["session_equal_mean"] > 0,
        "no_control_failure": controls["opposite_direction"]["verdict"] == "PASS",
    }
    structural = all(structural_gates.values())
    conditional_passed: list[str] = []
    tested = ["diagnostic_30_minute_universe_no_rescue"] + [f"{key}_no_rescue" for key in metrics["symbol_direction"]]
    primary_failed = primary["session_equal_mean"] <= 0
    if not primary_failed:
        for key, item in metrics["symbol_direction"].items():
            if (
                item["candidate_count"] >= C.CONDITIONAL_MIN_CANDIDATES
                and item["session_count"] >= C.CONDITIONAL_MIN_SESSIONS
                and item["holm"]["holm_adjusted_p"] <= C.HOLM_ALPHA
                and item["session_equal_mean_bps"] >= C.STRUCTURAL_MIN_MEAN_BPS
                and item["session_cluster_bootstrap"]["lower_bps"] > 0
            ):
                conditional_passed.append(key)
    verdict = "ORB_STRUCTURAL_EDGE_CANDIDATE" if structural else ("ORB_CONDITIONAL_EDGE_CANDIDATE" if conditional_passed else "ORB_NO_STRUCTURAL_EDGE")
    return {
        "verdict": verdict,
        "terminal_primary_rule_applied": primary_failed,
        "terminal_primary_rule": "IF primary 15-minute session-equal mean <= 0 THEN ORB_NO_STRUCTURAL_EDGE",
        "structural_gates": structural_gates,
        "structural_gates_passed": [key for key, value in structural_gates.items() if value],
        "structural_gates_failed": [key for key, value in structural_gates.items() if not value],
        "conditional_conditions_tested": tested,
        "conditional_conditions_passed": conditional_passed,
    }


def verdict_payload(metrics: dict[str, Any], controls: dict[str, Any], concentration: dict[str, Any], replication: dict[str, Any], overlap: dict[str, Any]) -> dict[str, Any]:
    result = structural_and_conditional(metrics, controls, concentration, replication, overlap)
    payload = {
        **evidence_header("ORB_EDGE_SCREEN_VERDICT_V1", result["verdict"], "applied frozen structural and conditional verdict gates to recomputed evidence"),
        **result,
        "next_action": "freeze ORB and select the next strategy" if result["verdict"] == "ORB_NO_STRUCTURAL_EDGE" else "human review, then WFA only",
    }
    payload["projection_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "projection_hash"}))
    return payload


def report_text(metrics: dict[str, Any], controls: dict[str, Any], concentration: dict[str, Any], replication: dict[str, Any], overlap: dict[str, Any], verdict: dict[str, Any]) -> str:
    primary = metrics["primary"]
    lines = [
        "# ORB Structural-Edge Screen v1",
        "",
        "- mode: ORB_EDGE_SCREEN_REPORT_V1",
        "- candidate_id: ALL_ORB_OUTCOME_V2_CANDIDATES",
        f"- decision: {verdict['verdict']}",
        "- reason: applied frozen structural and conditional verdict gates to recomputed evidence",
        f"- timestamp: {TIMESTAMP}",
        "- source: opening_range_retest_outcome_ledger_v2.json",
        "- is_order_action: false",
        "- broker_api_called: false",
        f"- verdict: {verdict['verdict']}",
        f"- primary_horizon_minutes: {C.PRIMARY_HORIZON}",
        f"- primary_candidate_count: {primary['candidate_count']}",
        f"- primary_session_equal_mean_bps: {primary['session_equal_mean_bps']:.6f}",
        f"- primary_ci_bps: [{primary['session_cluster_bootstrap']['lower_bps']:.6f}, {primary['session_cluster_bootstrap']['upper_bps']:.6f}]",
        f"- matched_time_coverage: {controls['matched_time']['coverage']:.6f}",
        f"- random_direction_p: {controls['random_direction']['permutation_p']:.6f}",
        f"- within_stratum_p: {controls['within_stratum_direction_permutation']['permutation_p']:.6f}",
        "",
        "This is pre-cost underlying-only research evidence. It is not option PnL, not profitability proof, and not paper/live readiness.",
        "",
        "## Failed Structural Gates",
    ]
    lines.extend(f"- {item}" for item in verdict["structural_gates_failed"])
    if verdict["verdict"] == "ORB_NO_STRUCTURAL_EDGE":
        lines.extend(["", "STOP ORB RESEARCH", "FREEZE ACCEPTED IMPLEMENTATION", "DO NOT TUNE ORB", "SELECT NEXT STRATEGY HYPOTHESIS"])
    lines.extend(
        [
            "",
            "## Agent Work Contract",
            "- source_agent: Codex",
            "- action: GENERATE_PATCH",
            "- scope: offline ORB structural-edge screen over certified outcome ledger only",
            "- allowed_paths: research/opening_range_retest_edge_screen_v1, scripts/*edge_screen_v1.py, tests/*edge_screen*, docs/agent_reviews/opening_range_retest_edge_screen_*_v1*",
            "- forbidden_paths: production strategy, core, config, broker, risk, feed, dashboard, runtime source data, Phase 1 v2 artifacts, Outcome v2 artifacts, PR #674",
            "",
            "## Scope Guard",
            "- production files touched: none",
            "- source data copied: none",
            "- source symlinks created: none",
            "- ORB tuning performed: none",
            "",
            "## Grill Me Review",
            "- Verdict is constrained by failed structural gates; no profitability, option PnL, WFA, paper, or live readiness claim is made.",
            "",
            "## Hermes Review",
            "- The workflow separates contract freeze, implementation freeze, deterministic evidence generation, and independent oracle audit.",
            "",
            "## GSD Review",
            "- Implementation stays inside the approved research, script, test, and evidence paths.",
            "",
            "## QA / Safety Review",
            "- Evidence is read-only, append=false, is_order_action=false, broker_api_called=false, and allowed_for_live_execution=false.",
            "",
            "## Acceptance Proof",
            "- Contract, metrics, controls, concentration, replication, overlap, verdict, audit, and report artifacts have SHA-256 sidecars.",
            "- Independent oracle verdict required: ORB_EDGE_SCREEN_AUDIT_CERTIFIED.",
            "",
            "## Runtime Proof Required After Merge",
            "- None. This PR is offline research evidence only and is not production integration.",
            "",
            "## What This PR Does Not Prove",
            "- It does not prove option profitability, transaction-cost survivability, WFA stability, paper readiness, live readiness, or production promotion.",
            "",
            "## Human Approval",
            "- Required before any WFA follow-up or next strategy-hypothesis selection work.",
        ]
    )
    return "\n".join(lines) + "\n"


def artifact_hashes(output_dir: Path) -> dict[str, str]:
    return {key: shafile(output_dir / filename) for key, filename in C.ARTIFACT_NAMES.items() if (output_dir / filename).exists()}


def generate(output_dir: Path, source_project_root: Path, artifact_dir: Path) -> dict[str, Any]:
    authority = verify_source_authority(artifact_dir)
    if authority["source_authority"]["failures"]:
        raise ValueError(f"SOURCE_AUTHORITY_FAILED:{authority['source_authority']['failures']}")
    ledger = authority["ledger"]
    contract_payload = C.contract_payload()
    metrics = metrics_payload(ledger)
    controls = controls_payload(ledger, source_project_root)
    concentration = concentration_payload(ledger)
    replication = replication_payload(ledger)
    overlap = overlap_payload(ledger, artifact_dir)
    verdict = verdict_payload(metrics, controls, concentration, replication, overlap)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / C.ARTIFACT_NAMES["contract"], contract_payload)
    write_json(output_dir / C.ARTIFACT_NAMES["metrics"], metrics)
    write_json(output_dir / C.ARTIFACT_NAMES["controls"], controls)
    write_json(output_dir / C.ARTIFACT_NAMES["concentration"], concentration)
    write_json(output_dir / C.ARTIFACT_NAMES["replication"], replication)
    write_json(output_dir / C.ARTIFACT_NAMES["overlap"], overlap)
    write_json(output_dir / C.ARTIFACT_NAMES["verdict"], verdict)
    write_text(output_dir / C.ARTIFACT_NAMES["report"], report_text(metrics, controls, concentration, replication, overlap, verdict))
    audit = audit_artifacts(output_dir, source_project_root, artifact_dir)
    write_json(output_dir / C.ARTIFACT_NAMES["audit"], audit)
    return {
        "verdict": verdict["verdict"],
        "audit_verdict": audit["verdict"],
        "audit_failures": audit["failures"],
        "projection_hash": verdict["projection_hash"],
        "hashes": artifact_hashes(output_dir),
    }


def audit_artifacts(output_dir: Path, source_project_root: Path, artifact_dir: Path) -> dict[str, Any]:
    failures = []
    authority = verify_source_authority(artifact_dir)["source_authority"]
    failures.extend(authority["failures"])
    for key, filename in C.ARTIFACT_NAMES.items():
        if key == "audit":
            continue
        path = output_dir / filename
        if not path.exists():
            failures.append(f"MISSING_ARTIFACT:{key}")
            continue
        side = verify_sidecar(path)
        if not side["sidecar_match"]:
            failures.append(f"SIDECAR_MISMATCH:{key}")
    try:
        metrics = load_json(output_dir / C.ARTIFACT_NAMES["metrics"])
        controls = load_json(output_dir / C.ARTIFACT_NAMES["controls"])
        concentration = load_json(output_dir / C.ARTIFACT_NAMES["concentration"])
        replication = load_json(output_dir / C.ARTIFACT_NAMES["replication"])
        overlap = load_json(output_dir / C.ARTIFACT_NAMES["overlap"])
        verdict = load_json(output_dir / C.ARTIFACT_NAMES["verdict"])
    except Exception as exc:
        return {"schema_version": C.SCHEMA_VERSION, "mode": "ORB_EDGE_SCREEN_AUDIT_V1", "verdict": "ORB_EDGE_SCREEN_AUDIT_FAILED", "failures": [f"ARTIFACT_LOAD_FAILED:{exc}"], **safety()}
    recomputed = verdict_payload(metrics, controls, concentration, replication, overlap)
    if recomputed["verdict"] != verdict.get("verdict"):
        failures.append("VERDICT_RECOMPUTE_MISMATCH")
    if metrics["primary"]["candidate_count"] != C.EXPECTED_MEASURED_COUNTS[C.PRIMARY_HORIZON]:
        failures.append("PRIMARY_MEASURED_COUNT_MISMATCH")
    if metrics["secondary"]["candidate_count"] != C.EXPECTED_MEASURED_COUNTS[C.SECONDARY_HORIZON]:
        failures.append("SECONDARY_MEASURED_COUNT_MISMATCH")
    if controls["opposite_direction"]["verdict"] != "PASS":
        failures.append("OPPOSITE_DIRECTION_FAILED")
    if controls["matched_time"]["coverage"] < 0 or controls["matched_time"]["coverage"] > 1:
        failures.append("MATCHED_TIME_COVERAGE_INVALID")
    return {
        **evidence_header("ORB_EDGE_SCREEN_AUDIT_V1", "ORB_EDGE_SCREEN_AUDIT_CERTIFIED" if not failures else "ORB_EDGE_SCREEN_AUDIT_FAILED", "independent audit recomputed artifact sidecars, authority checks, counts, controls, and verdict consistency"),
        "verdict": "ORB_EDGE_SCREEN_AUDIT_CERTIFIED" if not failures else "ORB_EDGE_SCREEN_AUDIT_FAILED",
        "failures": failures,
        "source_authority": authority,
        "artifact_hashes": artifact_hashes(output_dir),
    }


def determinism_check(dir_a: Path, dir_b: Path) -> dict[str, Any]:
    failures = []
    hashes_a = artifact_hashes(dir_a)
    hashes_b = artifact_hashes(dir_b)
    for key in C.ARTIFACT_NAMES:
        if hashes_a.get(key) != hashes_b.get(key):
            failures.append(f"ARTIFACT_HASH_MISMATCH:{key}")
    return {
        "verdict": "TWO_DIRECTORY_ORB_EDGE_SCREEN_DETERMINISM_PASS" if not failures else "TWO_DIRECTORY_ORB_EDGE_SCREEN_DETERMINISM_FAIL",
        "failures": failures,
        "hashes_a": hashes_a,
        "hashes_b": hashes_b,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source-project-root", default="/Users/madhuram/tradebot")
    parser.add_argument("--artifact-dir", default="docs/agent_reviews")
    args = parser.parse_args(argv)
    result = generate(Path(args.output_dir), Path(args.source_project_root), Path(args.artifact_dir))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
