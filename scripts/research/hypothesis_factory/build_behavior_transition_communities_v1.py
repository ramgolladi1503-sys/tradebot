#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

COMPONENT_ID = "BEHAVIOR_TRANSITION_COMMUNITY_BUILDER_V1"
OUTCOME_TERMS = ("forward_return", "future_return", "pnl", "profit", "outcome", "target", "label")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def reject_outcome_like(rows: list[dict[str, object]]) -> None:
    for row in rows:
        payload = json.dumps(row, sort_keys=True).lower()
        if any(term in payload for term in OUTCOME_TERMS):
            raise ValueError("outcome_like_input_rejected")


def entropy(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if total <= 0:
        return 0.0
    ent = 0.0
    for value in counter.values():
        p = value / total
        if p > 0:
            ent -= p * math.log2(p)
    return ent


def stable_hash(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_edges(episodes: list[dict[str, object]]) -> tuple[Counter[tuple[str, str]], dict[tuple[str, str], set[str]], dict[tuple[str, str], set[str]], Counter[str]]:
    edge_counts: Counter[tuple[str, str]] = Counter()
    edge_episodes: dict[tuple[str, str], set[str]] = defaultdict(set)
    edge_sessions: dict[tuple[str, str], set[str]] = defaultdict(set)
    node_counts: Counter[str] = Counter()
    for episode in episodes:
        seq = [str(x) for x in episode.get("state_sequence", [])]
        episode_id = str(episode.get("episode_id"))
        session = str(episode.get("session"))
        seen_nodes = set(seq)
        node_counts.update(seen_nodes)
        for a, b in zip(seq, seq[1:]):
            edge = (a, b)
            edge_counts[edge] += 1
            edge_episodes[edge].add(episode_id)
            edge_sessions[edge].add(session)
    return edge_counts, edge_episodes, edge_sessions, node_counts


def build_communities(
    episodes: list[dict[str, object]],
    min_edge_episode_support: int,
    min_edge_session_support: int,
    min_community_episode_support: int,
    min_community_session_support: int,
    min_supported_edges: int,
    max_communities: int,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    edge_counts, edge_episodes, edge_sessions, node_counts = build_edges(episodes)
    supported_edges = {
        edge: count
        for edge, count in edge_counts.items()
        if len(edge_episodes[edge]) >= min_edge_episode_support and len(edge_sessions[edge]) >= min_edge_session_support
    }

    incoming: dict[str, Counter[str]] = defaultdict(Counter)
    outgoing: dict[str, Counter[str]] = defaultdict(Counter)
    center_episode_support: dict[str, set[str]] = defaultdict(set)
    center_session_support: dict[str, set[str]] = defaultdict(set)

    for (src, dst), count in supported_edges.items():
        outgoing[src][dst] += count
        incoming[dst][src] += count
        for center in (src, dst):
            center_episode_support[center].update(edge_episodes[(src, dst)])
            center_session_support[center].update(edge_sessions[(src, dst)])

    communities: list[dict[str, object]] = []
    for center in sorted(set(incoming) | set(outgoing)):
        in_edges = incoming.get(center, Counter())
        out_edges = outgoing.get(center, Counter())
        supported_edge_count = len(in_edges) + len(out_edges)
        ep_support = center_episode_support.get(center, set())
        sess_support = center_session_support.get(center, set())
        if supported_edge_count < min_supported_edges:
            continue
        if len(ep_support) < min_community_episode_support or len(sess_support) < min_community_session_support:
            continue
        signature = {
            "center_state": center,
            "incoming_states": sorted(in_edges),
            "outgoing_states": sorted(out_edges),
        }
        community_id = "BDE2_TRANS_COMM_" + stable_hash(signature)[:16]
        communities.append(
            {
                "community_id": community_id,
                "component_id": COMPONENT_ID,
                "center_state": center,
                "incoming_states": sorted(in_edges),
                "outgoing_states": sorted(out_edges),
                "incoming_edge_counts": dict(sorted(in_edges.items())),
                "outgoing_edge_counts": dict(sorted(out_edges.items())),
                "supported_edge_count": supported_edge_count,
                "episode_support": len(ep_support),
                "distinct_session_support": len(sess_support),
                "center_episode_presence": node_counts[center],
                "incoming_entropy": entropy(in_edges),
                "outgoing_entropy": entropy(out_edges),
                "search_family_id": "BDE2_TRANSITION_COMMUNITY_FAMILY_V1",
                "direction": "UNKNOWN",
                "entry_concept": "NONE",
                "exit_concept": "NONE",
                "edge_claimed": False,
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "next_action": "COMPILE_OR_DEVELOPMENT_TEST_ONLY_AFTER_GOVERNED_REVIEW",
                "signature_sha256": stable_hash(signature),
            }
        )

    communities.sort(key=lambda c: (-int(c["distinct_session_support"]), -int(c["episode_support"]), str(c["center_state"])))
    return communities[:max_communities], {
        "raw_edges": len(edge_counts),
        "supported_edges": len(supported_edges),
        "raw_nodes": len(node_counts),
        "eligible_communities_before_cap": len(communities),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--episodes", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_episodes_v1.jsonl")
    parser.add_argument("--output", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_transition_communities_v1.jsonl")
    parser.add_argument("--min-edge-episode-support", type=int, default=25)
    parser.add_argument("--min-edge-session-support", type=int, default=20)
    parser.add_argument("--min-community-episode-support", type=int, default=40)
    parser.add_argument("--min-community-session-support", type=int, default=30)
    parser.add_argument("--min-supported-edges", type=int, default=2)
    parser.add_argument("--max-communities", type=int, default=25)
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    episodes_path = root / args.episodes
    output_path = root / args.output
    summary_path = output_path.with_name("NIFTY_behavior_transition_communities_v1_summary.json")

    result: dict[str, object] = {
        "schema_version": 1,
        "component_id": COMPONENT_ID,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "forward_outcomes_used": False,
        "locked_outcomes_accessed": False,
        "episodes_path": str(episodes_path),
        "status": "FAIL_CLOSED",
    }

    try:
        episodes = load_jsonl(episodes_path)
        reject_outcome_like(episodes)
        communities, graph_stats = build_communities(
            episodes,
            args.min_edge_episode_support,
            args.min_edge_session_support,
            args.min_community_episode_support,
            args.min_community_session_support,
            args.min_supported_edges,
            args.max_communities,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in communities),
            encoding="utf-8",
        )
        status = "TRANSITION_COMMUNITY_CANDIDATES_BUILT" if communities else "NO_SUPPORTED_TRANSITION_COMMUNITIES"
        result.update(
            {
                "status": status,
                "episodes_read": len(episodes),
                "episodes_sha256": sha256(episodes_path),
                "communities_path": str(output_path),
                "communities_sha256": sha256(output_path),
                "selected_communities": len(communities),
                "graph_stats": graph_stats,
                "min_edge_episode_support": args.min_edge_episode_support,
                "min_edge_session_support": args.min_edge_session_support,
                "min_community_episode_support": args.min_community_episode_support,
                "min_community_session_support": args.min_community_session_support,
                "min_supported_edges": args.min_supported_edges,
                "max_communities": args.max_communities,
                "search_pressure": {
                    "episodes_scanned": len(episodes),
                    **graph_stats,
                    "selected_communities": len(communities),
                },
                "next_action": "GOVERNED_DEVELOPMENT_OUTCOME_TEST" if communities else "NO_TRANSITION_COMMUNITY_CANDIDATES",
                "interpretation": "Outcome-free transition community mining from BDE2 episode state graphs. Communities describe recurrent graph neighborhoods only; no return, excursion, profitability, or edge label is computed.",
            }
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"TRANSITION_COMMUNITY_CANDIDATES_BUILT", "NO_SUPPORTED_TRANSITION_COMMUNITIES"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
