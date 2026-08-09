#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median

RUNNER_ID = "BEHAVIOR_SEQUENCE_DEVELOPMENT_OUTCOME_V1"
DATASET_SHA256 = "6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8"
DEFAULT_HORIZONS = (3, 6, 12, 18)
DEFAULT_EXCURSION_HORIZON = 12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bps(a: float, b: float) -> float | None:
    return (b / a - 1.0) * 10000.0 if math.isfinite(a) and math.isfinite(b) and a > 0 else None


def load_rows(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        src = list(csv.DictReader(handle))
    required = {"timestamp", "open", "high", "low", "close"}
    if not src or not required.issubset(src[0]):
        raise ValueError("dataset_schema_mismatch")
    rows: list[dict[str, object]] = []
    for idx, row in enumerate(src):
        try:
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        except Exception:
            continue
        if min(o, h, l, c) <= 0 or h < l:
            continue
        ts = row["timestamp"]
        rows.append({
            "row_index": len(rows),
            "source_row_index": idx,
            "timestamp": ts,
            "session": row.get("session") or ts[:10],
            "open": o,
            "high": h,
            "low": l,
            "close": c,
        })
    rows.sort(key=lambda r: str(r["timestamp"]))
    for idx, row in enumerate(rows):
        row["row_index"] = idx
    return rows


def load_jsonl(path: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                out.append(json.loads(line))
    return out


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_path(root: Path, value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else root / p


def is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    return any(haystack[i : i + n] == needle for i in range(0, len(haystack) - n + 1))


def summarize(xs: list[float | None]) -> dict[str, float | int | None]:
    vals = [x for x in xs if x is not None and math.isfinite(x)]
    if not vals:
        return {"n": 0, "mean": None, "median": None}
    return {"n": len(vals), "mean": mean(vals), "median": median(vals)}


def evaluate_match(rows: list[dict[str, object]], end_index: int, horizons: tuple[int, ...], excursion_horizon: int) -> dict[str, object]:
    base = rows[end_index]
    base_close = float(base["close"])
    session = str(base["session"])
    returns: dict[str, float | None] = {}
    for horizon in horizons:
        j = end_index + horizon
        returns[str(horizon)] = bps(base_close, float(rows[j]["close"])) if j < len(rows) and rows[j]["session"] == session else None
    hi = base_close
    lo = base_close
    bars = 0
    for j in range(end_index + 1, min(len(rows), end_index + 1 + excursion_horizon)):
        if rows[j]["session"] != session:
            break
        hi = max(hi, float(rows[j]["high"]))
        lo = min(lo, float(rows[j]["low"]))
        bars += 1
    up = bps(base_close, hi)
    dn_raw = bps(base_close, lo)
    return {
        "confirmation_timestamp": base["timestamp"],
        "confirmation_row_index": end_index,
        "returns_bps": returns,
        "up_excursion_bps": up,
        "down_excursion_bps": -dn_raw if dn_raw is not None else None,
        "excursion_bars_observed": bars,
    }


def rate_at(values: list[float | None], threshold: float) -> float | None:
    vals = [x for x in values if x is not None and math.isfinite(x)]
    if not vals:
        return None
    return sum(1 for x in vals if x >= threshold) / len(vals)


def controlled_verdict(summary: dict[str, object], gate: dict[str, object]) -> tuple[str, list[str], str | None]:
    reasons: list[str] = []
    matches = int(summary["matches"])
    sessions = int(summary["distinct_sessions"])
    if matches < int(gate["minimum_development_matches"]):
        reasons.append("INSUFFICIENT_DEVELOPMENT_MATCHES")
    if sessions < int(gate["minimum_distinct_development_sessions"]):
        reasons.append("INSUFFICIENT_DISTINCT_DEVELOPMENT_SESSIONS")

    ret6 = summary["ret6_bps"]
    ret12 = summary["ret12_bps"]
    med6 = ret6.get("median") if isinstance(ret6, dict) else None
    med12 = ret12.get("median") if isinstance(ret12, dict) else None
    direction = None
    if med6 is None or med12 is None:
        reasons.append("RETURN_MEDIAN_MISSING")
    elif med6 * med12 <= 0:
        reasons.append("RET6_RET12_SIGN_CONSISTENCY_FAIL")
    elif abs(float(med6)) < float(gate["minimum_abs_median_ret6_bps"]):
        reasons.append("RET6_MEDIAN_MAGNITUDE_GATE_FAIL")
    elif abs(float(med12)) < float(gate["minimum_abs_median_ret12_bps"]):
        reasons.append("RET12_MEDIAN_MAGNITUDE_GATE_FAIL")
    else:
        direction = "UP" if float(med6) > 0 and float(med12) > 0 else "DOWN"

    up20 = summary.get("up_excursion_rate_20bps")
    dn20 = summary.get("down_excursion_rate_20bps")
    up30 = summary.get("up_excursion_rate_30bps")
    dn30 = summary.get("down_excursion_rate_30bps")
    if direction == "UP":
        if up20 is None or dn20 is None or float(up20) - float(dn20) < float(gate["minimum_favorable_minus_adverse_20bps"]):
            reasons.append("20BPS_FAVORABLE_ADVERSE_ASYMMETRY_FAIL")
        if up30 is None or dn30 is None or float(up30) - float(dn30) < float(gate["minimum_favorable_minus_adverse_30bps"]):
            reasons.append("30BPS_FAVORABLE_ADVERSE_ASYMMETRY_FAIL")
    elif direction == "DOWN":
        if up20 is None or dn20 is None or float(dn20) - float(up20) < float(gate["minimum_favorable_minus_adverse_20bps"]):
            reasons.append("20BPS_FAVORABLE_ADVERSE_ASYMMETRY_FAIL")
        if up30 is None or dn30 is None or float(dn30) - float(up30) < float(gate["minimum_favorable_minus_adverse_30bps"]):
            reasons.append("30BPS_FAVORABLE_ADVERSE_ASYMMETRY_FAIL")
    else:
        reasons.append("NO_DIRECTION_INFERRED")

    return ("DEVELOPMENT_STRUCTURE_SUPPORTED" if not reasons else "DEVELOPMENT_STRUCTURE_REJECTED", reasons, direction)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--dataset", default="research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv")
    ap.add_argument("--episodes", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_episodes_v1.jsonl")
    ap.add_argument("--manifest", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_candidate_passport_manifest_v1.json")
    ap.add_argument("--output-dir", default="research/evidence/behavior_discovery_engine_v2")
    ap.add_argument("--instrument", default="NIFTY")
    ap.add_argument("--development-fraction", type=float, default=0.80)
    ap.add_argument("--excursion-horizon-bars", type=int, default=DEFAULT_EXCURSION_HORIZON)
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve()
    dataset = as_path(root, args.dataset)
    episodes_path = as_path(root, args.episodes)
    manifest_path = as_path(root, args.manifest)
    od = as_path(root, args.output_dir)
    od.mkdir(parents=True, exist_ok=True)

    gate = {
        "minimum_development_matches": 20,
        "minimum_distinct_development_sessions": 15,
        "minimum_abs_median_ret6_bps": 3.0,
        "minimum_abs_median_ret12_bps": 3.0,
        "minimum_favorable_minus_adverse_20bps": 0.10,
        "minimum_favorable_minus_adverse_30bps": 0.05,
        "maximum_supported_candidates_without_narrowing": 3,
    }
    result: dict[str, object] = {
        "schema_version": 1,
        "status": "FAIL_CLOSED",
        "runner_id": RUNNER_ID,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "forward_outcomes_computed": False,
        "locked_outcomes_accessed": False,
        "development_only": True,
        "gate": gate,
    }
    try:
        if sha256(dataset) != DATASET_SHA256:
            raise ValueError("dataset_hash_mismatch")
        rows = load_rows(dataset)
        sessions = sorted({str(r["session"]) for r in rows})
        cut = int(len(sessions) * args.development_fraction)
        development_sessions = set(sessions[:cut])
        locked_sessions = set(sessions[cut:])
        episodes = load_jsonl(episodes_path)
        manifest = load_json(manifest_path)
        passport_refs = manifest.get("manifest", [])
        if not isinstance(passport_refs, list):
            raise ValueError("manifest_entries_missing")
        passports = [load_json(as_path(root, str(ref["passport_path"]))) for ref in passport_refs]
        rows_by_index = {int(r["row_index"]): r for r in rows}

        per_candidate = []
        match_records = []
        locked_matches_skipped = 0
        for passport in passports:
            candidate_id = str(passport["candidate_id"])
            sequence = [str(x) for x in passport["sequence_definition"]["state_sequence"]]
            candidate_matches = []
            for episode in episodes:
                episode_sequence = [str(x) for x in episode.get("state_sequence", [])]
                if not is_subsequence(sequence, episode_sequence):
                    continue
                sess = str(episode["session"])
                if sess in locked_sessions:
                    locked_matches_skipped += 1
                    continue
                if sess not in development_sessions:
                    continue
                end_index = int(episode["end_row_index"])
                if end_index not in rows_by_index:
                    continue
                observed = evaluate_match(rows, end_index, DEFAULT_HORIZONS, int(args.excursion_horizon_bars))
                record = {
                    "candidate_id": candidate_id,
                    "episode_id": episode["episode_id"],
                    "session": sess,
                    "sequence": sequence,
                    "conservative_confirmation_rule": "episode_end_row_close_after_full_behavior_sequence_observed",
                    **observed,
                }
                candidate_matches.append(record)
                match_records.append(record)

            returns_by_horizon = {str(h): [m["returns_bps"][str(h)] for m in candidate_matches] for h in DEFAULT_HORIZONS}
            up = [m["up_excursion_bps"] for m in candidate_matches]
            dn = [m["down_excursion_bps"] for m in candidate_matches]
            summary = {
                "candidate_id": candidate_id,
                "sequence": sequence,
                "matches": len(candidate_matches),
                "distinct_sessions": len({m["session"] for m in candidate_matches}),
                "ret3_bps": summarize(returns_by_horizon["3"]),
                "ret6_bps": summarize(returns_by_horizon["6"]),
                "ret12_bps": summarize(returns_by_horizon["12"]),
                "ret18_bps": summarize(returns_by_horizon["18"]),
                "up_excursion_rate_20bps": rate_at(up, 20.0),
                "down_excursion_rate_20bps": rate_at(dn, 20.0),
                "up_excursion_rate_30bps": rate_at(up, 30.0),
                "down_excursion_rate_30bps": rate_at(dn, 30.0),
            }
            verdict, reasons, direction = controlled_verdict(summary, gate)
            summary.update({"verdict": verdict, "reasons": reasons, "inferred_direction": direction})
            per_candidate.append(summary)

        supported = [x for x in per_candidate if x["verdict"] == "DEVELOPMENT_STRUCTURE_SUPPORTED"]
        if not supported:
            next_action = "NO_DEVELOPMENT_SUPPORTED_BEHAVIOR_SEQUENCE_CANDIDATE"
            status = "DEVELOPMENT_OUTCOME_SCREEN_COMPLETE_NO_SURVIVOR"
        elif len(supported) > int(gate["maximum_supported_candidates_without_narrowing"]):
            next_action = "SELECTION_PRESSURE_TOO_HIGH_NARROW_BEFORE_LOCKED_ACCESS"
            status = "DEVELOPMENT_OUTCOME_SCREEN_COMPLETE_TOO_MANY_SURVIVORS"
        else:
            next_action = "ADVANCE_SUPPORTED_CANDIDATES_TO_BOUNDED_ANATOMY_NO_LOCKED_ACCESS_YET"
            status = "DEVELOPMENT_OUTCOME_SCREEN_COMPLETE_WITH_SURVIVORS"

        matches_path = od / f"{args.instrument}_behavior_sequence_development_matches_v1.jsonl"
        summaries_path = od / f"{args.instrument}_behavior_sequence_development_v1.json"
        matches_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in match_records), encoding="utf-8")
        result.update({
            "status": status,
            "forward_outcomes_computed": True,
            "forward_outcomes_scope": "development_sessions_only",
            "dataset_sha256": sha256(dataset),
            "episodes_sha256": sha256(episodes_path),
            "manifest_sha256": sha256(manifest_path),
            "sessions_total": len(sessions),
            "development_sessions": len(development_sessions),
            "locked_sessions": len(locked_sessions),
            "first_locked_session": sessions[cut] if cut < len(sessions) else None,
            "passport_count": len(passports),
            "candidate_summaries": per_candidate,
            "supported_candidates": supported,
            "supported_candidate_count": len(supported),
            "locked_candidate_matches_skipped_without_outcome_computation": locked_matches_skipped,
            "matches_path": str(matches_path),
            "matches_sha256": sha256(matches_path),
            "next_action": next_action,
            "interpretation": "Development-only outcome screen for frozen BDE2 sequence passports. Episode end is used as a conservative confirmation timestamp. Locked sessions are skipped without computing outcomes. This is not OOS/WFA, not execution viability, and not structural edge certification.",
        })
        summaries_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result["summary_path"] = str(summaries_path)
        result["summary_sha256"] = sha256(summaries_path)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
        failure_path = od / f"{args.instrument}_behavior_sequence_development_v1_summary.json"
        failure_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if str(result.get("status", "")).startswith("DEVELOPMENT_OUTCOME_SCREEN_COMPLETE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
