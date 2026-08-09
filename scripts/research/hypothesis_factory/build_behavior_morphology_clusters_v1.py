#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

COMPONENT_ID = "BEHAVIOR_MORPHOLOGY_CLUSTER_BUILDER_V1"
FORBIDDEN_OUTCOME_TOKENS = {"forward", "future", "outcome", "target", "profit", "pnl", "return_after", "mfe", "mae"}
STATE_FAMILIES = {
    "COMPRESSION": "COMPRESSION",
    "EXPANSION": "EXPANSION",
    "DIRECTIONAL_UP": "DIRECTIONAL",
    "DIRECTIONAL_DOWN": "DIRECTIONAL",
    "DIRECTIONAL_ACCELERATION": "DIRECTIONAL",
    "DIRECTIONAL_DECELERATION": "DIRECTIONAL",
    "UPPER_REJECTION": "REJECTION",
    "LOWER_REJECTION": "REJECTION",
    "UPSIDE_ESCAPE": "ESCAPE",
    "DOWNSIDE_ESCAPE": "ESCAPE",
    "FAILED_UPSIDE_ESCAPE": "FAILED_ESCAPE",
    "FAILED_DOWNSIDE_ESCAPE": "FAILED_ESCAPE",
    "RANGE_BALANCE": "BALANCE",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_hash(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                out.append(json.loads(line))
    return out


def reject_outcome_like_payload(records: list[dict[str, object]]) -> None:
    for record in records:
        payload = json.dumps(record, sort_keys=True).lower()
        if any(token in payload for token in FORBIDDEN_OUTCOME_TOKENS):
            raise ValueError("outcome_like_input_rejected")


def safe_mean(xs: list[float | None]) -> float | None:
    vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return sum(vals) / len(vals) if vals else None


def safe_median(xs: list[float | None]) -> float | None:
    vals = [float(x) for x in xs if x is not None and math.isfinite(float(x))]
    return float(median(vals)) if vals else None


def rate(count: int, denom: int) -> float:
    return count / denom if denom > 0 else 0.0


def share_bin(x: float) -> str:
    if x >= 0.50:
        return "HIGH"
    if x >= 0.20:
        return "MED"
    if x > 0.0:
        return "LOW"
    return "ZERO"


def sign_bin(x: float, deadband: float = 0.10) -> str:
    if x >= deadband:
        return "POS"
    if x <= -deadband:
        return "NEG"
    return "BAL"


def magnitude_bin(x: float | None, cut1: float, cut2: float) -> str:
    if x is None or not math.isfinite(x):
        return "NA"
    if x >= cut2:
        return "HIGH"
    if x >= cut1:
        return "MED"
    return "LOW"


def count_bin(x: int, cut1: int, cut2: int) -> str:
    if x >= cut2:
        return "HIGH"
    if x >= cut1:
        return "MED"
    return "LOW"


def dominant_family(states: list[str]) -> str:
    families = [STATE_FAMILIES.get(s, "OTHER") for s in states]
    if not families:
        return "NONE"
    return Counter(families).most_common(1)[0][0]


def episode_rows_for_episode(episode: dict[str, object], rows_by_index: dict[int, dict[str, object]]) -> list[dict[str, object]]:
    start = int(episode["start_row_index"])
    end = int(episode["end_row_index"])
    session = str(episode["session"])
    rows: list[dict[str, object]] = []
    for idx in range(start, end + 1):
        row = rows_by_index.get(idx)
        if row is not None and str(row.get("session")) == session:
            rows.append(row)
    return rows


def build_episode_morphology(episode: dict[str, object], rows: list[dict[str, object]]) -> dict[str, object]:
    row_states: list[str] = []
    for row in rows:
        row_states.extend(str(s) for s in row.get("states", []))
    counts = Counter(row_states)
    active_rows = [row for row in rows if row.get("states")]
    active_count = max(1, len(active_rows))
    state_sequence = [str(s) for s in episode.get("state_sequence", [])]
    first_family = dominant_family([state_sequence[0]]) if state_sequence else "NONE"
    last_family = dominant_family([state_sequence[-1]]) if state_sequence else "NONE"
    range_ratios = [row.get("features", {}).get("range_ratio") for row in rows if isinstance(row.get("features"), dict)]
    bar_rets = [abs(float(row.get("features", {}).get("bar_return_bps"))) for row in rows if isinstance(row.get("features"), dict) and row.get("features", {}).get("bar_return_bps") is not None]
    cc_rets = [abs(float(row.get("features", {}).get("close_to_close_return_bps"))) for row in rows if isinstance(row.get("features"), dict) and row.get("features", {}).get("close_to_close_return_bps") is not None]
    upper_wicks = [row.get("features", {}).get("upper_wick_fraction") for row in rows if isinstance(row.get("features"), dict)]
    lower_wicks = [row.get("features", {}).get("lower_wick_fraction") for row in rows if isinstance(row.get("features"), dict)]
    upper_mean = safe_mean(upper_wicks) or 0.0
    lower_mean = safe_mean(lower_wicks) or 0.0
    up_dir = counts["DIRECTIONAL_UP"] + counts["UPSIDE_ESCAPE"] + counts["FAILED_DOWNSIDE_ESCAPE"]
    down_dir = counts["DIRECTIONAL_DOWN"] + counts["DOWNSIDE_ESCAPE"] + counts["FAILED_UPSIDE_ESCAPE"]
    up_escape = counts["UPSIDE_ESCAPE"] + counts["FAILED_DOWNSIDE_ESCAPE"]
    down_escape = counts["DOWNSIDE_ESCAPE"] + counts["FAILED_UPSIDE_ESCAPE"]
    rejection_balance = counts["LOWER_REJECTION"] - counts["UPPER_REJECTION"]
    directional_balance = up_dir - down_dir
    escape_balance = up_escape - down_escape
    features = {
        "episode_id": episode["episode_id"],
        "session": episode["session"],
        "start_row_index": episode["start_row_index"],
        "end_row_index": episode["end_row_index"],
        "first_observable_timestamp": episode.get("first_observable_timestamp"),
        "end_timestamp": episode.get("end_timestamp"),
        "duration_bars": int(episode.get("duration_bars", 0)),
        "transition_count": int(episode.get("transition_count", 0)),
        "state_sequence_length": len(state_sequence),
        "state_set_count": len(episode.get("state_sets", [])),
        "active_row_count": active_count,
        "dominant_family": dominant_family(row_states),
        "first_family": first_family,
        "last_family": last_family,
        "compression_rate": rate(counts["COMPRESSION"], active_count),
        "expansion_rate": rate(counts["EXPANSION"], active_count),
        "range_balance_rate": rate(counts["RANGE_BALANCE"], active_count),
        "rejection_balance": rejection_balance / active_count,
        "directional_balance": directional_balance / active_count,
        "escape_balance": escape_balance / active_count,
        "failed_escape_rate": rate(counts["FAILED_UPSIDE_ESCAPE"] + counts["FAILED_DOWNSIDE_ESCAPE"], active_count),
        "median_range_ratio": safe_median(range_ratios),
        "max_range_ratio": max([float(x) for x in range_ratios if x is not None and math.isfinite(float(x))], default=None),
        "median_abs_bar_return_bps": safe_median(bar_rets),
        "median_abs_close_to_close_return_bps": safe_median(cc_rets),
        "wick_skew": lower_mean - upper_mean,
    }
    key = {
        "duration_bin": count_bin(int(features["duration_bars"]), 4, 9),
        "transition_bin": count_bin(int(features["transition_count"]), 2, 5),
        "sequence_len_bin": count_bin(int(features["state_sequence_length"]), 4, 8),
        "dominant_family": features["dominant_family"],
        "first_family": features["first_family"],
        "last_family": features["last_family"],
        "compression_bin": share_bin(float(features["compression_rate"])),
        "expansion_bin": share_bin(float(features["expansion_rate"])),
        "balance_bin": share_bin(float(features["range_balance_rate"])),
        "rejection_bias": sign_bin(float(features["rejection_balance"])),
        "directional_bias": sign_bin(float(features["directional_balance"])),
        "escape_bias": sign_bin(float(features["escape_balance"])),
        "failed_escape_bin": share_bin(float(features["failed_escape_rate"])),
        "range_ratio_bin": magnitude_bin(features["median_range_ratio"], 0.75, 1.25),
        "abs_ret_bin": magnitude_bin(features["median_abs_bar_return_bps"], 2.0, 5.0),
        "wick_skew_bin": sign_bin(float(features["wick_skew"]), 0.08),
    }
    features["morphology_key"] = key
    features["morphology_signature"] = stable_hash(key)[:16]
    return features


def summarize_cluster(signature: str, members: list[dict[str, object]]) -> dict[str, object]:
    sessions = {str(m["session"]) for m in members}
    numeric_fields = [
        "duration_bars",
        "transition_count",
        "state_sequence_length",
        "compression_rate",
        "expansion_rate",
        "range_balance_rate",
        "rejection_balance",
        "directional_balance",
        "escape_balance",
        "failed_escape_rate",
        "median_range_ratio",
        "max_range_ratio",
        "median_abs_bar_return_bps",
        "median_abs_close_to_close_return_bps",
        "wick_skew",
    ]
    centroid = {field: safe_mean([m.get(field) for m in members]) for field in numeric_fields}
    exemplar = sorted(members, key=lambda x: (str(x["session"]), int(x["start_row_index"])))[0]
    return {
        "cluster_id": f"BDE2_MORPH_{signature}",
        "morphology_signature": signature,
        "morphology_key": exemplar["morphology_key"],
        "episode_support": len(members),
        "distinct_sessions": len(sessions),
        "example_episode_id": exemplar["episode_id"],
        "first_observable_timestamp_min": min(str(m["first_observable_timestamp"]) for m in members),
        "first_observable_timestamp_max": max(str(m["first_observable_timestamp"]) for m in members),
        "centroid": centroid,
        "edge_claimed": False,
        "forward_outcomes_used": False,
        "locked_outcomes_accessed": False,
        "next_action": "GOVERNED_DEVELOPMENT_OUTCOME_TEST_ONLY_AFTER_PASSPORT_FREEZE",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--states", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_states_v1.jsonl")
    ap.add_argument("--episodes", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_episodes_v1.jsonl")
    ap.add_argument("--output", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_morphology_clusters_v1.jsonl")
    ap.add_argument("--features-output", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_episode_morphology_features_v1.jsonl")
    ap.add_argument("--min-episode-support", type=int, default=20)
    ap.add_argument("--min-distinct-session-support", type=int, default=15)
    ap.add_argument("--max-clusters", type=int, default=25)
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    states_path = root / args.states
    episodes_path = root / args.episodes
    output_path = root / args.output
    features_path = root / args.features_output
    summary_path = output_path.parent / "NIFTY_behavior_morphology_clusters_v1_summary.json"
    result = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "status": "FAIL_CLOSED",
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "forward_outcomes_used": False,
        "locked_outcomes_accessed": False,
    }
    try:
        states = load_jsonl(states_path)
        episodes = load_jsonl(episodes_path)
        reject_outcome_like_payload(states)
        reject_outcome_like_payload(episodes)
        rows_by_index = {int(row["row_index"]): row for row in states}
        feature_rows = [build_episode_morphology(ep, episode_rows_for_episode(ep, rows_by_index)) for ep in episodes]
        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in feature_rows:
            grouped[str(row["morphology_signature"])].append(row)
        raw_clusters = [summarize_cluster(sig, members) for sig, members in grouped.items()]
        eligible_clusters = [
            c for c in raw_clusters
            if int(c["episode_support"]) >= args.min_episode_support and int(c["distinct_sessions"]) >= args.min_distinct_session_support
        ]
        eligible_clusters.sort(key=lambda c: (-int(c["distinct_sessions"]), -int(c["episode_support"]), str(c["cluster_id"])))
        selected = eligible_clusters[: args.max_clusters]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        features_path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in feature_rows), encoding="utf-8")
        output_path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in selected), encoding="utf-8")
        result.update({
            "status": "BEHAVIOR_MORPHOLOGY_CLUSTERS_BUILT" if selected else "NO_SUPPORTED_MORPHOLOGY_CLUSTERS",
            "states_path": str(states_path),
            "states_sha256": sha256(states_path),
            "episodes_path": str(episodes_path),
            "episodes_sha256": sha256(episodes_path),
            "episodes_read": len(episodes),
            "episode_feature_rows": len(feature_rows),
            "raw_morphology_signatures": len(grouped),
            "eligible_clusters": len(eligible_clusters),
            "selected_clusters": len(selected),
            "min_episode_support": args.min_episode_support,
            "min_distinct_session_support": args.min_distinct_session_support,
            "max_clusters": args.max_clusters,
            "features_path": str(features_path),
            "features_sha256": sha256(features_path),
            "clusters_path": str(output_path),
            "clusters_sha256": sha256(output_path),
            "search_pressure": {
                "episodes_featurized": len(feature_rows),
                "raw_morphology_signatures": len(grouped),
                "eligible_clusters": len(eligible_clusters),
                "selected_clusters": len(selected),
            },
            "interpretation": "Outcome-free morphology clustering of BDE2 episodes. Features are derived only from observable state rows and episode structure. Frequency is not profitability and no edge is claimed.",
            "next_action": "FREEZE_MORPHOLOGY_CLUSTER_PASSPORTS" if selected else "NO_MORPHOLOGY_CLUSTER_CANDIDATES",
        })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"BEHAVIOR_MORPHOLOGY_CLUSTERS_BUILT", "NO_SUPPORTED_MORPHOLOGY_CLUSTERS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
