#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

RUNNER_ID = "BEHAVIOR_TRANSITION_COMMUNITY_DEVELOPMENT_OUTCOME_V1"
SEARCH_FAMILY_ID = "BDE2_TRANSITION_COMMUNITY_FAMILY_V1"
OUTCOME_SCOPE = "development_sessions_only"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_market_rows(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        raw = list(csv.DictReader(handle))
    required = {"timestamp", "open", "high", "low", "close"}
    if not raw or not required.issubset(raw[0]):
        raise ValueError("dataset_schema_mismatch")
    rows: list[dict[str, object]] = []
    for idx, row in enumerate(raw):
        try:
            open_px = float(row["open"])
            high_px = float(row["high"])
            low_px = float(row["low"])
            close_px = float(row["close"])
        except Exception:
            continue
        if min(open_px, high_px, low_px, close_px) <= 0 or high_px < low_px:
            continue
        timestamp = row["timestamp"]
        rows.append(
            {
                "row_index": len(rows),
                "timestamp": timestamp,
                "session": row.get("session") or timestamp[:10],
                "open": open_px,
                "high": high_px,
                "low": low_px,
                "close": close_px,
            }
        )
    rows.sort(key=lambda r: str(r["timestamp"]))
    for idx, row in enumerate(rows):
        row["row_index"] = idx
    return rows


def bps(base: float, px: float) -> float | None:
    if base > 0 and math.isfinite(base) and math.isfinite(px):
        return (px / base - 1.0) * 10000.0
    return None


def median(values: list[float]) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    mid = len(xs) // 2
    if len(xs) % 2:
        return xs[mid]
    return (xs[mid - 1] + xs[mid]) / 2.0


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(values: list[float]) -> dict[str, object]:
    return {"n": len(values), "mean": mean(values), "median": median(values)}


def ensure_candidate_safety(candidates: list[dict[str, object]]) -> None:
    for candidate in candidates:
        if candidate.get("edge_claimed") is not False:
            raise ValueError("candidate_edge_claim_must_be_false")
        if candidate.get("forward_outcomes_used") is not False:
            raise ValueError("candidate_forward_outcome_flag_must_be_false")
        if candidate.get("locked_outcomes_accessed") is not False:
            raise ValueError("candidate_locked_outcome_flag_must_be_false")
        if candidate.get("search_family_id") != SEARCH_FAMILY_ID:
            raise ValueError("candidate_search_family_mismatch")


def sessions_split(rows: list[dict[str, object]], development_fraction: float) -> tuple[set[str], set[str], str | None]:
    sessions = sorted({str(r["session"]) for r in rows})
    cut = max(1, int(len(sessions) * development_fraction))
    dev = set(sessions[:cut])
    locked = set(sessions[cut:])
    first_locked = sessions[cut] if cut < len(sessions) else None
    return dev, locked, first_locked


def edge_pairs(sequence: list[str]) -> list[tuple[str, str]]:
    return list(zip(sequence, sequence[1:]))


def episode_matches_candidate(episode: dict[str, object], candidate: dict[str, object]) -> bool:
    center = str(candidate.get("center_state"))
    seq = [str(x) for x in episode.get("state_sequence", [])]
    if center not in seq:
        return False
    incoming_allowed = {str(x) for x in candidate.get("incoming_states", [])}
    outgoing_allowed = {str(x) for x in candidate.get("outgoing_states", [])}
    pairs = edge_pairs(seq)
    has_incoming = any(dst == center and src in incoming_allowed for src, dst in pairs) if incoming_allowed else True
    has_outgoing = any(src == center and dst in outgoing_allowed for src, dst in pairs) if outgoing_allowed else True
    return has_incoming and has_outgoing


def compute_outcome(market_rows: list[dict[str, object]], row_index: int, horizons: tuple[int, ...]) -> dict[str, object]:
    base = float(market_rows[row_index]["close"])
    result: dict[str, object] = {}
    for horizon in horizons:
        idx = row_index + horizon
        result[f"ret{horizon}_bps"] = bps(base, float(market_rows[idx]["close"])) if idx < len(market_rows) else None
    excursion_window = market_rows[row_index + 1 : min(len(market_rows), row_index + 13)]
    up_vals = [bps(base, float(r["high"])) for r in excursion_window]
    down_vals = [bps(base, float(r["low"])) for r in excursion_window]
    result["max_up_12_bps"] = max([x for x in up_vals if x is not None], default=None)
    result["max_down_12_bps"] = min([x for x in down_vals if x is not None], default=None)
    return result


def infer_direction(ret6: float | None, ret12: float | None, up20: float, down20: float, up30: float, down30: float) -> str | None:
    if ret6 is None or ret12 is None:
        return None
    if ret6 >= 3.0 and ret12 >= 3.0 and (up20 - down20) >= 0.08 and (up30 - down30) >= 0.03:
        return "UP"
    if ret6 <= -3.0 and ret12 <= -3.0 and (down20 - up20) >= 0.08 and (down30 - up30) >= 0.03:
        return "DOWN"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--dataset", default="research/hypotheses/historical_corpus/kite_nifty_cache_v2/canonical/NIFTY.csv")
    parser.add_argument("--episodes", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_episodes_v1.jsonl")
    parser.add_argument("--candidates", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_transition_community_candidates_v1.jsonl")
    parser.add_argument("--output", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_transition_community_development_v1.json")
    parser.add_argument("--matches-output", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_transition_community_development_matches_v1.jsonl")
    parser.add_argument("--development-fraction", type=float, default=0.80)
    parser.add_argument("--minimum-development-matches", type=int, default=20)
    parser.add_argument("--minimum-distinct-development-sessions", type=int, default=15)
    parser.add_argument("--minimum-abs-median-ret6-bps", type=float, default=3.0)
    parser.add_argument("--minimum-abs-median-ret12-bps", type=float, default=3.0)
    parser.add_argument("--minimum-favorable-minus-adverse-20bps", type=float, default=0.08)
    parser.add_argument("--minimum-favorable-minus-adverse-30bps", type=float, default=0.03)
    parser.add_argument("--maximum-supported-candidates-without-narrowing", type=int, default=2)
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    dataset_path = root / args.dataset
    episodes_path = root / args.episodes
    candidates_path = root / args.candidates
    output_path = root / args.output
    matches_path = root / args.matches_output

    result: dict[str, object] = {
        "schema_version": 1,
        "runner_id": RUNNER_ID,
        "search_family_id": SEARCH_FAMILY_ID,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "development_only": True,
        "forward_outcomes_computed": True,
        "forward_outcomes_scope": OUTCOME_SCOPE,
        "locked_outcomes_accessed": False,
        "status": "FAIL_CLOSED",
    }

    try:
        market_rows = load_market_rows(dataset_path)
        episodes = load_jsonl(episodes_path)
        candidates = load_jsonl(candidates_path)
        ensure_candidate_safety(candidates)
        market_by_row = {int(r["row_index"]): r for r in market_rows}
        dev_sessions, locked_sessions, first_locked_session = sessions_split(market_rows, args.development_fraction)

        candidate_matches: dict[str, list[dict[str, object]]] = defaultdict(list)
        locked_skipped = 0
        match_rows: list[dict[str, object]] = []
        horizons = (3, 6, 12, 18)

        for episode in episodes:
            session = str(episode.get("session"))
            end_row_index = int(episode.get("end_row_index", -1))
            if end_row_index < 0 or end_row_index not in market_by_row:
                continue
            for candidate in candidates:
                if not episode_matches_candidate(episode, candidate):
                    continue
                if session in locked_sessions:
                    locked_skipped += 1
                    continue
                if session not in dev_sessions:
                    continue
                outcome = compute_outcome(market_rows, end_row_index, horizons)
                row = {
                    "candidate_id": candidate.get("candidate_id"),
                    "community_id": candidate.get("community_id"),
                    "center_state": candidate.get("center_state"),
                    "episode_id": episode.get("episode_id"),
                    "session": session,
                    "confirmation_row_index": end_row_index,
                    "confirmation_timestamp": episode.get("end_timestamp"),
                    **outcome,
                }
                candidate_matches[str(candidate.get("candidate_id"))].append(row)
                match_rows.append(row)

        summaries: list[dict[str, object]] = []
        supported: list[dict[str, object]] = []
        for candidate in candidates:
            cid = str(candidate.get("candidate_id"))
            rows = candidate_matches.get(cid, [])
            ret3 = [float(r["ret3_bps"]) for r in rows if r.get("ret3_bps") is not None]
            ret6 = [float(r["ret6_bps"]) for r in rows if r.get("ret6_bps") is not None]
            ret12 = [float(r["ret12_bps"]) for r in rows if r.get("ret12_bps") is not None]
            ret18 = [float(r["ret18_bps"]) for r in rows if r.get("ret18_bps") is not None]
            up12 = [float(r["max_up_12_bps"]) for r in rows if r.get("max_up_12_bps") is not None]
            down12 = [float(r["max_down_12_bps"]) for r in rows if r.get("max_down_12_bps") is not None]
            up20 = sum(1 for x in up12 if x >= 20.0) / len(up12) if up12 else 0.0
            up30 = sum(1 for x in up12 if x >= 30.0) / len(up12) if up12 else 0.0
            down20 = sum(1 for x in down12 if x <= -20.0) / len(down12) if down12 else 0.0
            down30 = sum(1 for x in down12 if x <= -30.0) / len(down12) if down12 else 0.0
            med6 = median(ret6)
            med12 = median(ret12)
            direction = infer_direction(med6, med12, up20, down20, up30, down30)
            distinct_sessions = len({str(r["session"]) for r in rows})
            reasons: list[str] = []
            if len(rows) < args.minimum_development_matches:
                reasons.append("MIN_DEVELOPMENT_MATCHES_FAIL")
            if distinct_sessions < args.minimum_distinct_development_sessions:
                reasons.append("MIN_DISTINCT_DEVELOPMENT_SESSIONS_FAIL")
            if med6 is None or abs(med6) < args.minimum_abs_median_ret6_bps:
                reasons.append("RET6_MEDIAN_MAGNITUDE_GATE_FAIL")
            if med12 is None or abs(med12) < args.minimum_abs_median_ret12_bps:
                reasons.append("RET12_MEDIAN_MAGNITUDE_GATE_FAIL")
            if med6 is not None and med12 is not None and med6 * med12 <= 0:
                reasons.append("RET6_RET12_SIGN_CONSISTENCY_FAIL")
            if direction == "UP":
                if (up20 - down20) < args.minimum_favorable_minus_adverse_20bps:
                    reasons.append("UP_EXCURSION_20BPS_ASYMMETRY_FAIL")
                if (up30 - down30) < args.minimum_favorable_minus_adverse_30bps:
                    reasons.append("UP_EXCURSION_30BPS_ASYMMETRY_FAIL")
            elif direction == "DOWN":
                if (down20 - up20) < args.minimum_favorable_minus_adverse_20bps:
                    reasons.append("DOWN_EXCURSION_20BPS_ASYMMETRY_FAIL")
                if (down30 - up30) < args.minimum_favorable_minus_adverse_30bps:
                    reasons.append("DOWN_EXCURSION_30BPS_ASYMMETRY_FAIL")
            else:
                reasons.append("NO_DIRECTION_INFERRED")

            summary = {
                "candidate_id": cid,
                "community_id": candidate.get("community_id"),
                "center_state": candidate.get("center_state"),
                "matches": len(rows),
                "distinct_sessions": distinct_sessions,
                "ret3_bps": summarize(ret3),
                "ret6_bps": summarize(ret6),
                "ret12_bps": summarize(ret12),
                "ret18_bps": summarize(ret18),
                "up_excursion_rate_20bps": up20,
                "down_excursion_rate_20bps": down20,
                "up_excursion_rate_30bps": up30,
                "down_excursion_rate_30bps": down30,
                "inferred_direction": direction,
                "reasons": reasons,
                "verdict": "DEVELOPMENT_STRUCTURE_SUPPORTED" if not reasons else "DEVELOPMENT_STRUCTURE_REJECTED",
            }
            summaries.append(summary)
            if not reasons:
                supported.append(summary)

        if len(supported) > args.maximum_supported_candidates_without_narrowing:
            status = "DEVELOPMENT_SUPPORTED_BUT_SELECTION_PRESSURE_TOO_HIGH"
            next_action = "NARROW_SUPPORTED_TRANSITION_COMMUNITIES_BEFORE_LOCKED_VALIDATION"
        elif supported:
            status = "DEVELOPMENT_STRUCTURE_SUPPORTED"
            next_action = "FREEZE_SUPPORTED_SPEC_BEFORE_LOCKED_VALIDATION"
        else:
            status = "DEVELOPMENT_OUTCOME_SCREEN_COMPLETE_NO_SURVIVOR"
            next_action = "NO_DEVELOPMENT_SUPPORTED_TRANSITION_COMMUNITY_CANDIDATE"

        matches_path.parent.mkdir(parents=True, exist_ok=True)
        matches_path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in match_rows), encoding="utf-8")
        result.update(
            {
                "status": status,
                "next_action": next_action,
                "dataset_sha256": sha256(dataset_path),
                "episodes_sha256": sha256(episodes_path),
                "candidates_sha256": sha256(candidates_path),
                "candidate_count": len(candidates),
                "sessions_total": len(dev_sessions) + len(locked_sessions),
                "development_sessions": len(dev_sessions),
                "locked_sessions": len(locked_sessions),
                "first_locked_session": first_locked_session,
                "locked_candidate_matches_skipped_without_outcome_computation": locked_skipped,
                "candidate_summaries": summaries,
                "supported_candidate_count": len(supported),
                "supported_candidates": supported,
                "matches_path": str(matches_path),
                "matches_sha256": sha256(matches_path),
                "summary_path": str(output_path),
                "gate": {
                    "minimum_development_matches": args.minimum_development_matches,
                    "minimum_distinct_development_sessions": args.minimum_distinct_development_sessions,
                    "minimum_abs_median_ret6_bps": args.minimum_abs_median_ret6_bps,
                    "minimum_abs_median_ret12_bps": args.minimum_abs_median_ret12_bps,
                    "minimum_favorable_minus_adverse_20bps": args.minimum_favorable_minus_adverse_20bps,
                    "minimum_favorable_minus_adverse_30bps": args.minimum_favorable_minus_adverse_30bps,
                    "maximum_supported_candidates_without_narrowing": args.maximum_supported_candidates_without_narrowing,
                },
                "interpretation": "Development-only outcome screen for selected BDE2 transition community candidates. Episode end is used as conservative confirmation. Locked sessions are skipped without computing outcomes. This is not OOS/WFA, not execution viability, and not structural edge certification.",
            }
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {
        "DEVELOPMENT_STRUCTURE_SUPPORTED",
        "DEVELOPMENT_SUPPORTED_BUT_SELECTION_PRESSURE_TOO_HIGH",
        "DEVELOPMENT_OUTCOME_SCREEN_COMPLETE_NO_SURVIVOR",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
