#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

SELECTOR_ID = "BEHAVIOR_SEQUENCE_CANDIDATE_SELECTOR_V1"
ANCHOR_STATES = {
    "COMPRESSION",
    "EXPANSION",
    "FAILED_DOWNSIDE_ESCAPE",
    "FAILED_UPSIDE_ESCAPE",
    "DOWNSIDE_ESCAPE",
    "UPSIDE_ESCAPE",
    "LOWER_REJECTION",
    "UPPER_REJECTION",
}
GENERIC_DIRECTIONAL_STATES = {
    "DIRECTIONAL_UP",
    "DIRECTIONAL_DOWN",
    "DIRECTIONAL_ACCELERATION",
    "DIRECTIONAL_DECELERATION",
    "RANGE_BALANCE",
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


def is_subsequence(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    if len(a) > len(b):
        return False
    return any(tuple(b[i : i + len(a)]) == a for i in range(0, len(b) - len(a) + 1))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def mine_with_support(
    episodes: list[dict[str, object]],
    min_len: int,
    max_len: int,
    min_support: int,
    min_sessions: int,
) -> list[dict[str, object]]:
    episode_support: dict[tuple[str, ...], set[str]] = defaultdict(set)
    session_support: dict[tuple[str, ...], set[str]] = defaultdict(set)
    duration_bars: dict[tuple[str, ...], list[int]] = defaultdict(list)
    example_episode: dict[tuple[str, ...], str] = {}

    for episode in episodes:
        sequence = tuple(str(x) for x in episode.get("state_sequence", []))
        if len(sequence) < min_len:
            continue
        seen: set[tuple[str, ...]] = set()
        for n in range(min_len, min(max_len, len(sequence)) + 1):
            for i in range(0, len(sequence) - n + 1):
                candidate = tuple(sequence[i : i + n])
                if candidate in seen:
                    continue
                seen.add(candidate)
                episode_support[candidate].add(str(episode["episode_id"]))
                session_support[candidate].add(str(episode["session"]))
                try:
                    duration_bars[candidate].append(int(episode.get("duration_bars", 0)))
                except Exception:
                    pass
                example_episode.setdefault(candidate, str(episode["episode_id"]))

    raw: list[dict[str, object]] = []
    for seq, eps in episode_support.items():
        sessions = session_support[seq]
        if len(eps) < min_support or len(sessions) < min_sessions:
            continue
        anchor_count = sum(1 for x in seq if x in ANCHOR_STATES)
        generic_count = sum(1 for x in seq if x in GENERIC_DIRECTIONAL_STATES)
        if anchor_count < 2:
            continue
        if generic_count == len(seq):
            continue
        ds = duration_bars.get(seq, [])
        avg_duration = sum(ds) / len(ds) if ds else None
        raw.append(
            {
                "schema_version": 1,
                "selector_id": SELECTOR_ID,
                "sequence_id": f"SEQ_{stable_hash({'sequence': seq})[:16]}",
                "state_sequence": list(seq),
                "sequence_length": len(seq),
                "episode_support": len(eps),
                "distinct_session_support": len(sessions),
                "support_episode_ids": sorted(eps),
                "support_sessions": sorted(sessions),
                "example_episode_id": example_episode.get(seq),
                "anchor_state_count": anchor_count,
                "generic_directional_state_count": generic_count,
                "average_episode_duration_bars": avg_duration,
                "direction": "UNKNOWN",
                "entry_concept": "NONE",
                "exit_concept": "NONE",
                "forward_outcomes_used": False,
                "edge_claimed": False,
            }
        )
    raw.sort(
        key=lambda r: (
            -int(r["distinct_session_support"]),
            -int(r["anchor_state_count"]),
            -int(r["sequence_length"]),
            -int(r["episode_support"]),
            str(r["sequence_id"]),
        )
    )
    return raw


def select_distinct(records: list[dict[str, object]], max_candidates: int, max_jaccard: float) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    selected: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    first_state_counts: Counter[str] = Counter()
    anchor_signature_counts: Counter[str] = Counter()

    for record in records:
        seq = tuple(str(x) for x in record["state_sequence"])
        first_state = seq[0]
        anchor_signature = "+".join(sorted(x for x in seq if x in ANCHOR_STATES))
        reason = None
        if first_state_counts[first_state] >= 4:
            reason = "FIRST_STATE_CONCENTRATION_LIMIT"
        elif anchor_signature_counts[anchor_signature] >= 3:
            reason = "ANCHOR_SIGNATURE_CONCENTRATION_LIMIT"
        else:
            eps = set(str(x) for x in record.get("support_episode_ids", []))
            for kept in selected:
                kept_seq = tuple(str(x) for x in kept["state_sequence"])
                kept_eps = set(str(x) for x in kept.get("support_episode_ids", []))
                if is_subsequence(seq, kept_seq) or is_subsequence(kept_seq, seq):
                    if jaccard(eps, kept_eps) >= max_jaccard:
                        reason = "REDUNDANT_SUBSEQUENCE_OR_SUPERSEQUENCE"
                        break
                if jaccard(eps, kept_eps) >= 0.95:
                    reason = "EPISODE_SUPPORT_NEAR_DUPLICATE"
                    break
        if reason:
            reject_record = {k: v for k, v in record.items() if k not in {"support_episode_ids", "support_sessions"}}
            reject_record["rejection_reason"] = reason
            rejected.append(reject_record)
            continue
        selected.append(record)
        first_state_counts[first_state] += 1
        anchor_signature_counts[anchor_signature] += 1
        if len(selected) >= max_candidates:
            break
    return selected, rejected


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--episodes", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_episodes_v1.jsonl")
    ap.add_argument("--output-dir", default="research/evidence/behavior_discovery_engine_v2")
    ap.add_argument("--instrument", default="NIFTY")
    ap.add_argument("--min-len", type=int, default=3)
    ap.add_argument("--max-len", type=int, default=5)
    ap.add_argument("--min-support", type=int, default=12)
    ap.add_argument("--min-sessions", type=int, default=10)
    ap.add_argument("--max-candidates", type=int, default=25)
    ap.add_argument("--max-overlap-jaccard", type=float, default=0.80)
    args = ap.parse_args(argv)

    root = Path(args.repo_root).resolve()
    ep = Path(args.episodes)
    ep = ep if ep.is_absolute() else root / ep
    od = root / args.output_dir
    od.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": 1,
        "status": "FAIL_CLOSED",
        "selector_id": SELECTOR_ID,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "forward_outcomes_used": False,
        "locked_outcomes_accessed": False,
    }
    try:
        episodes = load_jsonl(ep)
        dumped_keys = json.dumps([sorted(e.keys()) for e in episodes]).lower()
        for token in ("forward", "future", "pnl", "profit", "outcome", "target", "label"):
            if token in dumped_keys:
                raise ValueError(f"outcome_like_episode_key_rejected:{token}")
        raw = mine_with_support(episodes, args.min_len, args.max_len, args.min_support, args.min_sessions)
        selected, rejected = select_distinct(raw, args.max_candidates, args.max_overlap_jaccard)
        out = od / f"{args.instrument}_behavior_sequence_candidates_v1.jsonl"
        rejection_path = od / f"{args.instrument}_behavior_sequence_candidates_v1_rejections.jsonl"
        summary_path = od / f"{args.instrument}_behavior_sequence_candidates_v1_summary.json"
        out.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in selected),
            encoding="utf-8",
        )
        rejection_path.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rejected),
            encoding="utf-8",
        )
        result.update(
            {
                "status": "BEHAVIOR_SEQUENCE_CANDIDATES_SELECTED" if selected else "NO_DISTINCT_BEHAVIOR_SEQUENCE_CANDIDATES",
                "episodes_path": str(ep),
                "episodes_sha256": sha256(ep),
                "episodes_read": len(episodes),
                "raw_recurrent_sequences_after_structural_gates": len(raw),
                "selected_candidates": len(selected),
                "rejected_as_redundant_or_concentrated": len(rejected),
                "selection_policy": {
                    "min_len": args.min_len,
                    "max_len": args.max_len,
                    "min_episode_support": args.min_support,
                    "min_distinct_session_support": args.min_sessions,
                    "max_candidates": args.max_candidates,
                    "max_overlap_jaccard": args.max_overlap_jaccard,
                    "minimum_anchor_state_count": 2,
                    "generic_directional_only_sequences_rejected": True,
                    "first_state_concentration_limit": 4,
                    "anchor_signature_concentration_limit": 3,
                },
                "search_pressure": {
                    "episodes_scanned": len(episodes),
                    "sequence_lengths_tried": args.max_len - args.min_len + 1,
                    "raw_recurrent_sequences_after_structural_gates": len(raw),
                    "selected_candidates": len(selected),
                },
                "candidate_sequences_path": str(out),
                "candidate_sequences_sha256": sha256(out),
                "rejections_path": str(rejection_path),
                "rejections_sha256": sha256(rejection_path),
                "next_action": "COMPILE_SELECTED_BEHAVIOR_HYPOTHESIS_PASSPORTS" if selected else "NO_OUTCOME_ACCESS_REVIEW_DISCOVERY_GEOMETRY",
                "interpretation": "Pre-outcome selector for materially distinct recurrent behavior sequences. This reduces false-discovery pressure before any development outcome test and still does not claim edge.",
            }
        )
        summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result["summary_path"] = str(summary_path)
        result["summary_sha256"] = sha256(summary_path)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"BEHAVIOR_SEQUENCE_CANDIDATES_SELECTED", "NO_DISTINCT_BEHAVIOR_SEQUENCE_CANDIDATES"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
