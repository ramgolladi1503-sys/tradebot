#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
from datetime import datetime
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

EXPECTED_GENERATION = "RAJ_ARORA_EXTERNAL_SEEDED_PROXY_V1_FREEZE"
EXPECTED_DATASET_SHA = "6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8"
IST = ZoneInfo("Asia/Kolkata")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_ts(value: str) -> datetime:
    s = (value or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    return dt


def num(row: dict, key: str) -> float:
    try:
        return float(row[key])
    except Exception:
        return float("nan")


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    required = {"timestamp", "open", "high", "low", "close"}
    if not raw or not required.issubset(raw[0]):
        raise ValueError("dataset_schema_mismatch")
    rows = []
    for r in raw:
        ts = parse_ts(r["timestamp"])
        o, h, l, c = (num(r, k) for k in ("open", "high", "low", "close"))
        if not all(math.isfinite(x) and x > 0 for x in (o, h, l, c)) or h < max(o, c) or l > min(o, c):
            raise ValueError(f"invalid_ohlc:{r.get('timestamp')}")
        rows.append({"timestamp": ts, "session": ts.date().isoformat(), "open": o, "high": h, "low": l, "close": c})
    rows.sort(key=lambda r: r["timestamp"])
    return rows


def session_map(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        out.setdefault(row["session"], []).append(row)
    for session, bars in out.items():
        for i in range(1, len(bars)):
            if bars[i]["timestamp"] <= bars[i - 1]["timestamp"]:
                raise ValueError(f"non_monotonic_session:{session}")
    return out


def valid_opening_prefix(bars: list[dict], n: int) -> bool:
    if len(bars) <= n:
        return False
    if bars[0]["timestamp"].astimezone(IST).strftime("%H:%M") != "09:15":
        return False
    for i in range(1, n):
        delta = (bars[i]["timestamp"] - bars[i - 1]["timestamp"]).total_seconds()
        if delta != 300:
            return False
    return True


def first_or_retest_continuation(bars: list[dict], cfg: dict) -> tuple[int, int] | None:
    n = int(cfg["or_bars"])
    if not valid_opening_prefix(bars, n):
        return None
    hi = max(x["high"] for x in bars[:n])
    lo = min(x["low"] for x in bars[:n])
    buffer = float(cfg["breakout_buffer_bps"]) / 10000.0
    breakout = None
    direction = 0
    for i in range(n, len(bars)):
        if bars[i]["close"] > hi * (1.0 + buffer):
            breakout, direction = i, 1
            break
        if bars[i]["close"] < lo * (1.0 - buffer):
            breakout, direction = i, -1
            break
    if breakout is None:
        return None

    retest = None
    retest_max = int(cfg["retest_max_bars"])
    for j in range(breakout + 1, min(len(bars), breakout + 1 + retest_max)):
        b = bars[j]
        if direction > 0:
            if b["close"] < hi:
                return None
            if b["low"] <= hi and b["close"] >= hi and b["low"] > lo:
                retest = j
                break
        else:
            if b["close"] > lo:
                return None
            if b["high"] >= lo and b["close"] <= lo and b["high"] < hi:
                retest = j
                break
    if retest is None:
        return None

    cont_max = int(cfg["continuation_max_bars"])
    for k in range(retest + 1, min(len(bars), retest + 1 + cont_max)):
        b = bars[k]
        if direction > 0:
            if b["close"] < hi:
                return None
            if b["close"] > bars[retest]["high"]:
                return k, direction
        else:
            if b["close"] > lo:
                return None
            if b["close"] < bars[retest]["low"]:
                return k, direction
    return None


def first_or_failed_breakout(bars: list[dict], cfg: dict) -> tuple[int, int] | None:
    n = int(cfg["or_bars"])
    if not valid_opening_prefix(bars, n):
        return None
    hi = max(x["high"] for x in bars[:n])
    lo = min(x["low"] for x in bars[:n])
    buffer = float(cfg["breakout_buffer_bps"]) / 10000.0
    breakout = None
    breakout_dir = 0
    for i in range(n, len(bars)):
        if bars[i]["close"] > hi * (1.0 + buffer):
            breakout, breakout_dir = i, 1
            break
        if bars[i]["close"] < lo * (1.0 - buffer):
            breakout, breakout_dir = i, -1
            break
    if breakout is None:
        return None

    max_bars = int(cfg["failure_max_bars"])
    for j in range(breakout + 1, min(len(bars), breakout + 1 + max_bars)):
        c = bars[j]["close"]
        if lo <= c <= hi:
            return j, -breakout_dir
    return None


def first_opening_drive_pullback_resumption(bars: list[dict], cfg: dict) -> tuple[int, int] | None:
    n = int(cfg["drive_bars"])
    if not valid_opening_prefix(bars, n):
        return None
    origin = bars[0]["open"]
    end = bars[n - 1]["close"]
    move = end - origin
    move_bps = abs(move) / origin * 10000.0
    if move_bps < float(cfg["drive_min_bps"]) or move == 0:
        return None
    direction = 1 if move > 0 else -1
    magnitude = abs(move)
    min_r = float(cfg["min_retrace_fraction"])
    max_r = float(cfg["max_retrace_fraction"])
    pullback_max = int(cfg["pullback_max_bars"])

    pullback = None
    for j in range(n, min(len(bars), n + pullback_max)):
        b = bars[j]
        prev = bars[j - 1]
        if direction > 0:
            retrace = (end - b["low"]) / magnitude
            counter = b["close"] < prev["close"]
            not_erased = b["low"] > origin
        else:
            retrace = (b["high"] - end) / magnitude
            counter = b["close"] > prev["close"]
            not_erased = b["high"] < origin
        if counter and not_erased and min_r <= retrace <= max_r:
            pullback = j
            break
    if pullback is None:
        return None

    resume_max = int(cfg["resumption_max_bars"])
    for k in range(pullback + 1, min(len(bars), pullback + 1 + resume_max)):
        if direction > 0 and bars[k]["close"] > bars[pullback]["high"]:
            return k, direction
        if direction < 0 and bars[k]["close"] < bars[pullback]["low"]:
            return k, direction
    return None


def signal(passport_id: str, bars: list[dict], cfg: dict) -> tuple[int, int] | None:
    if passport_id == "RAJ_PROXY_OPENING_RANGE_BREAKOUT_RETEST_CONTINUATION":
        return first_or_retest_continuation(bars, cfg)
    if passport_id == "RAJ_PROXY_OPENING_RANGE_FAILED_BREAKOUT_REVERSAL":
        return first_or_failed_breakout(bars, cfg)
    if passport_id == "RAJ_PROXY_OPENING_DRIVE_PULLBACK_RESUMPTION":
        return first_opening_drive_pullback_resumption(bars, cfg)
    raise ValueError(f"unknown_passport:{passport_id}")


def expand_grid(passport: dict, horizons: list[int]) -> list[dict]:
    grid = passport["grid"]
    keys = sorted(grid)
    rows = []
    for values in itertools.product(*(grid[k] for k in keys)):
        base = dict(zip(keys, values))
        base.update(passport.get("fixed", {}))
        for horizon in horizons:
            rows.append({**base, "horizon_bars": int(horizon)})
    return rows


def evaluate(groups: dict[str, list[dict]], sessions: list[str], passport_id: str, cfg: dict, cost_bps: float) -> dict:
    returns = []
    horizon = int(cfg["horizon_bars"])
    for session in sessions:
        bars = groups[session]
        found = signal(passport_id, bars, cfg)
        if found is None:
            continue
        decision, direction = found
        entry = decision + 1
        exit_ = entry + horizon
        if exit_ >= len(bars):
            continue
        p0 = bars[entry]["close"]
        p1 = bars[exit_]["close"]
        returns.append(direction * ((p1 - p0) / p0) * 10000.0 - float(cost_bps))
    if not returns:
        return {"trades": 0, "mean_net_bps": None, "win_rate": None, "total_net_bps": None}
    return {
        "trades": len(returns),
        "mean_net_bps": mean(returns),
        "win_rate": sum(x > 0 for x in returns) / len(returns),
        "total_net_bps": sum(returns),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--freeze", default="research/strategy_certification/passports/RAJ_ARORA_EXTERNAL_SEEDED_PROXY_V1_FREEZE.json")
    ap.add_argument("--dataset")
    ap.add_argument("--output", default="research/evidence/strategy_certification/RAJ_ARORA_EXTERNAL_SEEDED_PROXY_V1_DEVELOPMENT.json")
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve()
    freeze_path = root / args.freeze
    result = {
        "status": "FAIL_CLOSED",
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "validation_accessed": False,
        "holdout_accessed": False,
        "exact_video_strategy_claimed": False,
    }

    try:
        frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
        if frozen.get("generation_id") != EXPECTED_GENERATION:
            raise ValueError("generation_id_mismatch")
        if frozen.get("dataset_sha256") != EXPECTED_DATASET_SHA:
            raise ValueError("freeze_dataset_hash_mismatch")
        dataset = root / (args.dataset or frozen["dataset_path"])
        if sha256(dataset) != EXPECTED_DATASET_SHA:
            raise ValueError("dataset_hash_mismatch")

        rows = load_rows(dataset)
        groups = session_map(rows)
        sessions = sorted(groups)
        if len(rows) != int(frozen["expected_rows"]):
            raise ValueError(f"row_count_mismatch:{len(rows)}")
        if len(sessions) != int(frozen["expected_sessions"]):
            raise ValueError(f"session_count_mismatch:{len(sessions)}")

        nd = int(len(sessions) * frozen["split_contract"]["development_fraction"])
        nv = int(len(sessions) * frozen["split_contract"]["validation_fraction"])
        dev_sessions = sessions[:nd]
        horizons = frozen["execution_contract"]["development_horizons_bars"]
        cost = float(frozen["execution_contract"]["base_round_trip_cost_bps"])
        gate = frozen["development_gate"]

        candidates = []
        cells = 0
        for passport in frozen["passports"]:
            pid = passport["passport_id"]
            all_results = []
            for cfg in expand_grid(passport, horizons):
                metrics = evaluate(groups, dev_sessions, pid, cfg, cost)
                all_results.append({"config": cfg, "metrics": metrics})
                cells += 1
            eligible = [
                x for x in all_results
                if x["metrics"]["trades"] >= int(gate["minimum_trades"])
                and x["metrics"]["mean_net_bps"] is not None
                and x["metrics"]["mean_net_bps"] > 0
            ]
            eligible.sort(key=lambda x: (x["metrics"]["mean_net_bps"], x["metrics"]["trades"]), reverse=True)
            nomination = eligible[0] if eligible else None
            candidates.append({
                "passport_id": pid,
                "development_status": "NOMINATED_FOR_VALIDATION" if nomination else "REJECTED_IN_DEVELOPMENT",
                "configs_tested": len(all_results),
                "nomination": nomination,
                "all_development_results": all_results,
            })

        declared_cells = int(frozen["search_budget"]["total_development_cells"])
        if cells != declared_cells:
            raise ValueError(f"search_budget_mismatch:{cells}!={declared_cells}")

        result.update({
            "status": "DEVELOPMENT_SCREEN_COMPLETE",
            "generation_id": EXPECTED_GENERATION,
            "dataset_sha256": sha256(dataset),
            "generation_sha256": sha256(freeze_path),
            "rows_total": len(rows),
            "sessions_total": len(sessions),
            "development_sessions": nd,
            "validation_sessions_reserved": nv,
            "holdout_sessions_reserved": len(sessions) - nd - nv,
            "development_cells_evaluated": cells,
            "candidates": candidates,
            "nominated_count": sum(x["development_status"] == "NOMINATED_FOR_VALIDATION" for x in candidates),
            "parameters_tuned": False,
            "next_action": "FREEZE_NOMINATION_AND_RUN_PREDECLARED_ROBUSTNESS_BEFORE_VALIDATION" if any(x["development_status"] == "NOMINATED_FOR_VALIDATION" for x in candidates) else "CLOSE_EXTERNAL_SEEDED_PROXY_V1_NO_DEVELOPMENT_SURVIVOR",
        })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"

    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "DEVELOPMENT_SCREEN_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
