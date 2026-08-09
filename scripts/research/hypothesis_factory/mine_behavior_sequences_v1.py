#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter, defaultdict
from pathlib import Path

MINER_ID = "BEHAVIOR_SEQUENCE_MINER_V1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    out = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                out.append(json.loads(line))
    return out


def sequence_hash(sequence: tuple[str, ...]) -> str:
    payload = json.dumps({"sequence": sequence}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def mine_sequences(episodes: list[dict[str, object]], min_len: int = 2, max_len: int = 5, min_support: int = 8, min_sessions: int = 5) -> list[dict[str, object]]:
    support: Counter[tuple[str, ...]] = Counter()
    session_support: dict[tuple[str, ...], set[str]] = defaultdict(set)
    example_episode: dict[tuple[str, ...], str] = {}
    for episode in episodes:
        seq = [str(x) for x in episode.get("state_sequence", [])]
        if len(seq) < min_len:
            continue
        seen_in_episode: set[tuple[str, ...]] = set()
        for n in range(min_len, min(max_len, len(seq)) + 1):
            for i in range(0, len(seq) - n + 1):
                s = tuple(seq[i:i+n])
                if s in seen_in_episode:
                    continue
                seen_in_episode.add(s)
                support[s] += 1
                session_support[s].add(str(episode["session"]))
                example_episode.setdefault(s, str(episode["episode_id"]))
    records: list[dict[str, object]] = []
    for seq, count in support.items():
        sessions = session_support[seq]
        if count < min_support or len(sessions) < min_sessions:
            continue
        parent_support = 0
        if len(seq) > min_len:
            parents = [seq[:-1], seq[1:]]
            parent_support = max((support.get(p, 0) for p in parents), default=0)
        redundancy_ratio = (count / parent_support) if parent_support else None
        records.append({
            "schema_version": 1,
            "miner_id": MINER_ID,
            "sequence_id": f"SEQ_{sequence_hash(seq)}",
            "state_sequence": list(seq),
            "sequence_length": len(seq),
            "episode_support": count,
            "distinct_session_support": len(sessions),
            "example_episode_id": example_episode.get(seq),
            "redundancy_ratio_vs_strongest_parent": redundancy_ratio,
            "direction": "UNKNOWN",
            "entry_concept": "NONE",
            "exit_concept": "NONE",
            "forward_outcomes_used": False,
            "edge_claimed": False,
        })
    records.sort(key=lambda r: (-int(r["distinct_session_support"]), -int(r["episode_support"]), int(r["sequence_length"]), str(r["sequence_id"])))
    return records


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--episodes", required=True)
    ap.add_argument("--output-dir", default="research/evidence/behavior_discovery_engine_v2")
    ap.add_argument("--instrument", default="NIFTY")
    ap.add_argument("--min-len", type=int, default=2)
    ap.add_argument("--max-len", type=int, default=5)
    ap.add_argument("--min-support", type=int, default=8)
    ap.add_argument("--min-sessions", type=int, default=5)
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    ep = Path(args.episodes)
    ep = ep if ep.is_absolute() else root / ep
    od = root / args.output_dir
    od.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 1, "status": "FAIL_CLOSED", "miner_id": MINER_ID, "runtime_authority": "NONE", "broker_actions_permitted": False, "edge_claimed": False, "forward_outcomes_used": False, "locked_outcomes_accessed": False}
    try:
        episodes = load_jsonl(ep)
        if any(e.get("forward_outcomes_used") for e in episodes):
            raise ValueError("episode_input_contains_forward_outcomes")
        records = mine_sequences(episodes, args.min_len, args.max_len, args.min_support, args.min_sessions)
        out = od / f"{args.instrument}_behavior_sequences_v1.jsonl"
        out.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")
        result.update({
            "status": "BEHAVIOR_SEQUENCES_MINED",
            "episodes_path": str(ep),
            "episodes_sha256": sha256(ep),
            "episodes_read": len(episodes),
            "sequence_records": len(records),
            "sequence_lengths_considered": list(range(args.min_len, args.max_len + 1)),
            "min_episode_support": args.min_support,
            "min_distinct_session_support": args.min_sessions,
            "search_pressure": {"sequence_lengths_tried": args.max_len - args.min_len + 1, "episodes_scanned": len(episodes), "candidate_sequences_retained": len(records)},
            "sequences_path": str(out),
            "sequences_sha256": sha256(out),
            "next_action": "COMPILE_BEHAVIOR_HYPOTHESIS_PASSPORTS" if records else "NO_RECURRENT_SEQUENCE_CANDIDATES",
            "interpretation": "Recurrent causal behavior sequences only. Frequency is not profitability and no outcome labels were read.",
        })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
    summary = od / f"{args.instrument}_behavior_sequences_v1_summary.json"
    summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "BEHAVIOR_SEQUENCES_MINED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
