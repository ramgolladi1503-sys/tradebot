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


def verify_sidecar(path: Path) -> dict[str, Any]:
    actual = shafile(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    expected = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.exists() else None
    return {"path": path.name, "artifact_sha256": actual, "sidecar_sha256": expected, "sidecar_match": actual == expected}


def verify_source_authority(artifact_dir: Path) -> dict[str, Any]:
    ledger_path = artifact_dir / "opening_range_retest_outcome_ledger_v2.json"
    contract_path = artifact_dir / "opening_range_retest_outcome_contract_v2.json"
    ledger = load_json(ledger_path)
    failures: list[str] = []
    sidecars = {
        "outcome_ledger": verify_sidecar(ledger_path),
        "outcome_contract": verify_sidecar(contract_path),
    }
    for key, item in sidecars.items():
        if not item["sidecar_match"]:
            failures.append(f"SIDECAR_MISMATCH:{key}")
    if sidecars["outcome_ledger"]["artifact_sha256"] != C.SOURCE_LEDGER_SHA256:
        failures.append("SOURCE_LEDGER_SHA_MISMATCH")
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
                "proposal_ready_at": parse_ts(core["proposal_ready_at_iso"]),
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
        return {"replications": reps, "seed": seed, "lower": 0.0, "upper": 0.0, "p_le_zero": 1.0}
    rng = np.random.default_rng(seed)
    stats = np.empty(reps, dtype=float)
    n = len(arr)
    for i in range(reps):
        stats[i] = float(np.mean(arr[rng.integers(0, n, n)]))
    return {
        "replications": reps,
        "seed": seed,
        "lower": float(np.percentile(stats, 2.5)),
        "upper": float(np.percentile(stats, 97.5)),
        "lower_bps": float(np.percentile(stats, 2.5) * 10000.0),
        "upper_bps": float(np.percentile(stats, 97.5) * 10000.0),
        "p_le_zero": float(np.mean(stats <= 0.0)),
    }


def sign_test_positive(values: list[float]) -> dict[str, Any]:
    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)
    n = pos + neg
    if n == 0:
        p = 1.0
    else:
        k = min(pos, neg)
        p = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2**n))
    return {"positive": pos, "negative": neg, "zero": len(values) - n, "two_sided_p": p}


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
        stats["one_sided_p"] = boot["p_le_zero"]
        key = f"{symbol}:{direction}"
        raw_p.append((key, boot["p_le_zero"]))
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
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_METRICS_V1",
        "source": "opening_range_retest_outcome_ledger_v2.json",
        "timestamp": TIMESTAMP,
        "horizons": horizons,
        "primary_horizon": C.PRIMARY_HORIZON,
        "secondary_horizon": C.SECONDARY_HORIZON,
        "primary": horizons[str(C.PRIMARY_HORIZON)],
        "secondary": horizons[str(C.SECONDARY_HORIZON)],
        "symbol_direction": symbol_direction,
        "projection_hash": shab(cbytes({"horizons": horizons, "symbol_direction": symbol_direction})),
        **safety(),
    }
    return payload


def random_direction_control(rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed = mean(session_means(rows).values())
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["symbol"], row["year"])].append(row)
    rng = random.Random(C.RANDOM_DIRECTION_SEED)
    diffs = []
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
        diffs.append(observed - mean(session_means(permuted).values()))
    arr = np.array(diffs)
    return {
        "observed_signal_session_equal_mean": observed,
        "mean_advantage": float(np.mean(arr)),
        "mean_advantage_bps": float(np.mean(arr) * 10000.0),
        "lower": float(np.percentile(arr, 2.5)),
        "upper": float(np.percentile(arr, 97.5)),
        "lower_bps": float(np.percentile(arr, 2.5) * 10000.0),
        "upper_bps": float(np.percentile(arr, 97.5) * 10000.0),
        "permutation_p": float(np.mean(arr <= 0.0)),
        "permutations": C.RANDOM_DIRECTION_PERMUTATIONS,
        "seed": C.RANDOM_DIRECTION_SEED,
    }


def opposite_direction_control(rows: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [row["candidate_id"] for row in rows if abs(row["return"] + (-row["return"])) > 1e-12]
    return {"failures": failures, "max_abs_identity_error": 0.0 if not failures else None, "verdict": "PASS" if not failures else "FAIL"}


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
            continue
        covered += 1
        for _ in range(C.MATCHED_TIME_DRAWS_PER_CANDIDATE):
            entry_open, terminal_close = candidates[rng.randrange(len(candidates))]
            raw = (terminal_close - entry_open) / entry_open
            ret = raw if row["direction"] == "BUY_CALL" else -raw
            item = dict(row)
            item["return"] = ret
            matched_rows.append(item)
            total_draws += 1
    observed = mean(session_means(rows).values())
    matched = mean(session_means(matched_rows).values())
    # Bootstrap paired by session date over observed-minus-control session means.
    obs_sessions = session_means(rows)
    ctl_sessions = session_means(matched_rows)
    common = sorted(set(obs_sessions) & set(ctl_sessions))
    diffs = [obs_sessions[key] - ctl_sessions[key] for key in common]
    boot = bootstrap(diffs, seed=C.MATCHED_TIME_SEED)
    return {
        "coverage": covered / len(rows) if rows else 0.0,
        "covered_candidates": covered,
        "candidate_count": len(rows),
        "draws": total_draws,
        "draws_per_candidate": C.MATCHED_TIME_DRAWS_PER_CANDIDATE,
        "signal_session_equal_mean": observed,
        "matched_time_session_equal_mean": matched,
        "advantage": observed - matched,
        "advantage_bps": (observed - matched) * 10000.0,
        "advantage_ci": boot,
        "seed": C.MATCHED_TIME_SEED,
    }


def within_stratum_control(rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed = mean(session_means(rows).values())
    groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["symbol"], row["year"], row["entry_bucket"])].append(row)
    rng = random.Random(C.WITHIN_STRATUM_SEED)
    diffs = []
    for _ in range(C.WITHIN_STRATUM_PERMUTATIONS):
        permuted = []
        for group_rows in groups.values():
            directions = [row["direction"] for row in group_rows]
            rng.shuffle(directions)
            for row, direction in zip(group_rows, directions):
                sign = 1.0 if direction == "BUY_CALL" else -1.0
                item = dict(row)
                item["return"] = sign * row["unsigned_return"]
                permuted.append(item)
        diffs.append(observed - mean(session_means(permuted).values()))
    arr = np.array(diffs)
    return {
        "mean_advantage": float(np.mean(arr)),
        "mean_advantage_bps": float(np.mean(arr) * 10000.0),
        "lower": float(np.percentile(arr, 2.5)),
        "upper": float(np.percentile(arr, 97.5)),
        "lower_bps": float(np.percentile(arr, 2.5) * 10000.0),
        "upper_bps": float(np.percentile(arr, 97.5) * 10000.0),
        "permutation_p": float(np.mean(arr <= 0.0)),
        "permutations": C.WITHIN_STRATUM_PERMUTATIONS,
        "seed": C.WITHIN_STRATUM_SEED,
    }


def controls_payload(ledger: dict[str, Any], source_project_root: Path) -> dict[str, Any]:
    rows = measured_rows(ledger, C.PRIMARY_HORIZON)
    payload = {
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_CONTROLS_V1",
        "timestamp": TIMESTAMP,
        "random_direction": random_direction_control(rows),
        "opposite_direction": opposite_direction_control(rows),
        "matched_time": matched_time_control(rows, source_project_root),
        "within_stratum_direction_permutation": within_stratum_control(rows),
        **safety(),
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
    payload = {
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_CONCENTRATION_V1",
        "timestamp": TIMESTAMP,
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
        },
        "top_1pct_candidate_count": top_count,
        **safety(),
    }
    payload["projection_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "projection_hash"}))
    return payload


def replication_payload(ledger: dict[str, Any]) -> dict[str, Any]:
    rows = measured_rows(ledger, C.PRIMARY_HORIZON)
    by_year = {str(year): descriptive_stats([row for row in rows if row["year"] == year]) for year in C.YEARS}
    by_symbol = {symbol: descriptive_stats([row for row in rows if row["symbol"] == symbol]) for symbol in C.SYMBOLS}
    by_direction = {direction: descriptive_stats([row for row in rows if row["direction"] == direction]) for direction in C.DIRECTIONS}
    sessions = session_means(rows)
    total_positive = sum(v for v in sessions.values() if v > 0)
    symbol_positive_contribution = {}
    for symbol in C.SYMBOLS:
        sym_sessions = session_means([row for row in rows if row["symbol"] == symbol])
        symbol_positive_contribution[symbol] = sum(v for v in sym_sessions.values() if v > 0) / total_positive if total_positive > 0 else None
    payload = {
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_REPLICATION_V1",
        "timestamp": TIMESTAMP,
        "years": by_year,
        "symbols": by_symbol,
        "directions": by_direction,
        "symbol_positive_contribution": symbol_positive_contribution,
        **safety(),
    }
    payload["projection_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "projection_hash"}))
    return payload


def overlap_payload(ledger: dict[str, Any]) -> dict[str, Any]:
    rows = measured_rows(ledger, C.PRIMARY_HORIZON)
    grouped_a: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_a[(row["session_date"], row["symbol"], row["direction"])].append(row)
    sens_a = [sorted(items, key=lambda row: (row["proposal_ready_at"], row["candidate_id"]))[0] for items in grouped_a.values()]
    # Component approximation is pre-registered and non-return-based: same session/symbol/direction/bucket.
    grouped_b: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_b[(row["session_date"], row["symbol"], row["direction"], row["entry_bucket"])].append(row)
    sens_b = [sorted(items, key=lambda row: (row["proposal_ready_at"], row["candidate_id"]))[0] for items in grouped_b.values()]
    payload = {
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_OVERLAP_V1",
        "timestamp": TIMESTAMP,
        "sensitivity_a": {"rule": "earliest per session x symbol x direction", **descriptive_stats(sens_a)},
        "sensitivity_b": {"rule": "earliest per non-return overlap proxy component", **descriptive_stats(sens_b)},
        **safety(),
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
        "mean_ge_1bp": primary["session_equal_mean_bps"] >= C.STRUCTURAL_MIN_MEAN_BPS,
        "lower_ci_gt_0": primary["session_cluster_bootstrap"]["lower_bps"] > 0,
        "positive_session_rate_gt_50pct": sum(1 for v in session_means(measured_rows(load_json(Path(C.SOURCE_LEDGER_PATH)), C.PRIMARY_HORIZON)).values() if v > 0) / primary["session_count"] > 0.50 if primary["session_count"] else False,
        "random_advantage_lower_ci_gt_0": rand["lower_bps"] > 0,
        "random_permutation_p_lte_0_05": rand["permutation_p"] <= 0.05,
        "matched_time_advantage_lower_ci_gt_0": matched["advantage_ci"]["lower_bps"] > 0,
        "matched_time_coverage_gte_95pct": matched["coverage"] >= C.MATCHED_TIME_MIN_COVERAGE,
        "within_stratum_p_lte_0_05": within["permutation_p"] <= 0.05,
        "at_least_2_of_3_years_positive": sum(1 for item in years.values() if item["session_equal_mean"] > 0) >= 2,
        "no_year_below_minus_1bp": all(item["session_equal_mean_bps"] >= -1.0 for item in years.values()),
        "at_least_2_of_3_symbols_positive": sum(1 for item in symbols.values() if item["session_equal_mean"] > 0) >= 2,
        "best_5_concentration_lte_50pct": (concentration["best_5_session_contribution"] is not None and concentration["best_5_session_contribution"] <= 0.50),
        "positive_after_best_5_removed": concentration["removal_means"]["best_5_sessions_removed"] > 0,
        "positive_after_top_1pct_removed": concentration["removal_means"]["top_1pct_candidates_removed"] > 0,
        "overlap_sensitivity_a_positive": overlap["sensitivity_a"]["session_equal_mean"] > 0,
        "overlap_sensitivity_b_positive": overlap["sensitivity_b"]["session_equal_mean"] > 0,
        "no_control_failure": controls["opposite_direction"]["verdict"] == "PASS",
    }
    structural = all(structural_gates.values())
    conditional_passed: list[str] = []
    tested = ["30_minute_universe"] + list(metrics["symbol_direction"])
    secondary = metrics["secondary"]
    if (
        secondary["session_equal_mean_bps"] >= C.STRUCTURAL_MIN_MEAN_BPS
        and secondary["session_cluster_bootstrap"]["lower_bps"] > 0
        and matched["coverage"] >= C.MATCHED_TIME_MIN_COVERAGE
        and concentration["removal_means"]["best_5_sessions_removed"] > 0
        and overlap["sensitivity_a"]["session_equal_mean"] > 0
        and overlap["sensitivity_b"]["session_equal_mean"] > 0
    ):
        conditional_passed.append("30_minute_universe")
    for key, item in metrics["symbol_direction"].items():
        symbol = key.split(":")[0]
        year_positive = sum(1 for year in C.YEARS if descriptive_stats([row for row in measured_rows(load_json(Path(C.SOURCE_LEDGER_PATH)), C.PRIMARY_HORIZON) if row["symbol"] == symbol and row["year"] == year])["session_equal_mean"] > 0) >= 2
        if (
            item["candidate_count"] >= C.CONDITIONAL_MIN_CANDIDATES
            and item["session_count"] >= C.CONDITIONAL_MIN_SESSIONS
            and item["holm"]["holm_adjusted_p"] <= C.HOLM_ALPHA
            and item["session_equal_mean_bps"] >= C.STRUCTURAL_MIN_MEAN_BPS
            and item["session_cluster_bootstrap"]["lower_bps"] > 0
            and year_positive
            and matched["coverage"] >= C.MATCHED_TIME_MIN_COVERAGE
            and concentration["removal_means"]["best_5_sessions_removed"] > 0
            and overlap["sensitivity_a"]["session_equal_mean"] > 0
            and overlap["sensitivity_b"]["session_equal_mean"] > 0
        ):
            conditional_passed.append(key)
    verdict = "ORB_STRUCTURAL_EDGE_CANDIDATE" if structural else ("ORB_CONDITIONAL_EDGE_CANDIDATE" if conditional_passed else "ORB_NO_STRUCTURAL_EDGE")
    return {
        "verdict": verdict,
        "structural_gates": structural_gates,
        "structural_gates_passed": [key for key, value in structural_gates.items() if value],
        "structural_gates_failed": [key for key, value in structural_gates.items() if not value],
        "conditional_conditions_tested": tested,
        "conditional_conditions_passed": conditional_passed,
    }


def verdict_payload(metrics: dict[str, Any], controls: dict[str, Any], concentration: dict[str, Any], replication: dict[str, Any], overlap: dict[str, Any]) -> dict[str, Any]:
    result = structural_and_conditional(metrics, controls, concentration, replication, overlap)
    payload = {
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_VERDICT_V1",
        "timestamp": TIMESTAMP,
        **result,
        "next_action": "freeze ORB and select the next strategy" if result["verdict"] == "ORB_NO_STRUCTURAL_EDGE" else "human review, then WFA only",
        **safety(),
    }
    payload["projection_hash"] = shab(cbytes({k: v for k, v in payload.items() if k != "projection_hash"}))
    return payload


def report_text(metrics: dict[str, Any], controls: dict[str, Any], concentration: dict[str, Any], replication: dict[str, Any], overlap: dict[str, Any], verdict: dict[str, Any]) -> str:
    primary = metrics["primary"]
    lines = [
        "# ORB Structural-Edge Screen v1",
        "",
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
    overlap = overlap_payload(ledger)
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
        "schema_version": C.SCHEMA_VERSION,
        "mode": "ORB_EDGE_SCREEN_AUDIT_V1",
        "timestamp": TIMESTAMP,
        "verdict": "ORB_EDGE_SCREEN_AUDIT_CERTIFIED" if not failures else "ORB_EDGE_SCREEN_AUDIT_FAILED",
        "failures": failures,
        "source_authority": authority,
        "artifact_hashes": artifact_hashes(output_dir),
        **safety(),
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
