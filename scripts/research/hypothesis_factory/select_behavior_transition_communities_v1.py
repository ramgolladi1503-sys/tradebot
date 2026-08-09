#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SELECTOR_ID = "BEHAVIOR_TRANSITION_COMMUNITY_SELECTOR_V1"
SEARCH_FAMILY_ID = "BDE2_TRANSITION_COMMUNITY_FAMILY_V1"
HIGH_INFORMATION_STATES = {
    "EXPANSION",
    "DOWNSIDE_ESCAPE",
    "UPSIDE_ESCAPE",
    "FAILED_DOWNSIDE_ESCAPE",
    "FAILED_UPSIDE_ESCAPE",
}
GENERIC_CENTER_STATES = {
    "COMPRESSION",
    "LOWER_REJECTION",
    "UPPER_REJECTION",
    "DIRECTIONAL_ACCELERATION",
    "DIRECTIONAL_DECELERATION",
    "DIRECTIONAL_DOWN",
    "DIRECTIONAL_UP",
    "RANGE_BALANCE",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_hash(obj: object) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def reject_outcome_like(rows: list[dict[str, object]]) -> None:
    terms = ("forward_return", "future_return", "pnl", "profit", "outcome", "target", "label")
    for row in rows:
        payload = json.dumps(row, sort_keys=True).lower()
        if any(term in payload for term in terms):
            raise ValueError("outcome_like_input_rejected")


def reject_reason(
    community: dict[str, object],
    total_sessions: int,
    max_session_fraction: float,
    min_episode_support: int,
    min_session_support: int,
    max_episode_presence: int,
    min_supported_edges: int,
    max_supported_edges: int,
) -> str | None:
    center = str(community.get("center_state"))
    episode_support = int(community.get("episode_support", 0))
    session_support = int(community.get("distinct_session_support", 0))
    center_presence = int(community.get("center_episode_presence", 0))
    supported_edges = int(community.get("supported_edge_count", 0))
    incoming = set(str(x) for x in community.get("incoming_states", []))
    outgoing = set(str(x) for x in community.get("outgoing_states", []))
    touched_states = incoming | outgoing | {center}

    if center in GENERIC_CENTER_STATES:
        return "GENERIC_CENTER_STATE"
    if center not in HIGH_INFORMATION_STATES:
        return "CENTER_NOT_HIGH_INFORMATION_STATE"
    if total_sessions > 0 and session_support / total_sessions > max_session_fraction:
        return "UBIQUITOUS_SESSION_SUPPORT"
    if episode_support < min_episode_support:
        return "MIN_EPISODE_SUPPORT_FAIL"
    if session_support < min_session_support:
        return "MIN_SESSION_SUPPORT_FAIL"
    if center_presence > max_episode_presence:
        return "CENTER_EPISODE_PRESENCE_TOO_BROAD"
    if supported_edges < min_supported_edges:
        return "MIN_SUPPORTED_EDGES_FAIL"
    if supported_edges > max_supported_edges:
        return "SUPPORTED_EDGES_TOO_BROAD"
    if not (touched_states & HIGH_INFORMATION_STATES):
        return "NO_HIGH_INFORMATION_NEIGHBORHOOD_STATE"
    return None


def score_candidate(community: dict[str, object], total_sessions: int) -> tuple[float, dict[str, float]]:
    session_support = float(community.get("distinct_session_support", 0))
    episode_support = float(community.get("episode_support", 0))
    center_presence = float(community.get("center_episode_presence", 0))
    supported_edges = float(community.get("supported_edge_count", 0))
    incoming_entropy = float(community.get("incoming_entropy", 0.0))
    outgoing_entropy = float(community.get("outgoing_entropy", 0.0))

    rarity = 1.0 - (session_support / total_sessions) if total_sessions > 0 else 0.0
    support = min(session_support / 120.0, 1.0)
    edge_focus = 1.0 / (1.0 + abs(supported_edges - 8.0) / 8.0)
    entropy_focus = 1.0 / (1.0 + ((incoming_entropy + outgoing_entropy) / 2.0))
    presence_focus = 1.0 / (1.0 + max(center_presence - episode_support, 0.0) / max(episode_support, 1.0))
    score = 0.30 * rarity + 0.25 * support + 0.20 * edge_focus + 0.15 * entropy_focus + 0.10 * presence_focus
    return score, {
        "rarity_component": rarity,
        "support_component": support,
        "edge_focus_component": edge_focus,
        "entropy_focus_component": entropy_focus,
        "presence_focus_component": presence_focus,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--communities", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_transition_communities_v1.jsonl")
    parser.add_argument("--output", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_transition_community_candidates_v1.jsonl")
    parser.add_argument("--rejections", default="research/evidence/behavior_discovery_engine_v2/NIFTY_behavior_transition_community_candidates_v1_rejections.jsonl")
    parser.add_argument("--max-session-fraction", type=float, default=0.90)
    parser.add_argument("--min-episode-support", type=int, default=60)
    parser.add_argument("--min-session-support", type=int, default=40)
    parser.add_argument("--max-episode-presence", type=int, default=650)
    parser.add_argument("--min-supported-edges", type=int, default=3)
    parser.add_argument("--max-supported-edges", type=int, default=16)
    parser.add_argument("--max-candidates", type=int, default=5)
    args = parser.parse_args(argv)

    root = Path(args.repo_root).resolve()
    communities_path = root / args.communities
    output_path = root / args.output
    rejections_path = root / args.rejections
    summary_path = output_path.with_name("NIFTY_behavior_transition_community_candidates_v1_summary.json")

    result: dict[str, object] = {
        "schema_version": 1,
        "selector_id": SELECTOR_ID,
        "search_family_id": SEARCH_FAMILY_ID,
        "runtime_authority": "NONE",
        "broker_actions_permitted": False,
        "edge_claimed": False,
        "forward_outcomes_used": False,
        "locked_outcomes_accessed": False,
        "communities_path": str(communities_path),
        "status": "FAIL_CLOSED",
    }

    try:
        communities = load_jsonl(communities_path)
        reject_outcome_like(communities)
        total_sessions = max((int(c.get("distinct_session_support", 0)) for c in communities), default=0)
        accepted: list[dict[str, object]] = []
        rejected: list[dict[str, object]] = []

        for community in communities:
            reason = reject_reason(
                community,
                total_sessions,
                args.max_session_fraction,
                args.min_episode_support,
                args.min_session_support,
                args.max_episode_presence,
                args.min_supported_edges,
                args.max_supported_edges,
            )
            if reason:
                rejected.append({
                    "community_id": community.get("community_id"),
                    "center_state": community.get("center_state"),
                    "reason": reason,
                    "episode_support": community.get("episode_support"),
                    "distinct_session_support": community.get("distinct_session_support"),
                    "center_episode_presence": community.get("center_episode_presence"),
                    "supported_edge_count": community.get("supported_edge_count"),
                })
                continue
            score, components = score_candidate(community, total_sessions)
            row = dict(community)
            row.update({
                "candidate_id": "BDE2_TRANS_CAND_" + stable_hash({
                    "community_id": community.get("community_id"),
                    "center_state": community.get("center_state"),
                    "signature_sha256": community.get("signature_sha256"),
                    "selector_id": SELECTOR_ID,
                })[:16],
                "selector_id": SELECTOR_ID,
                "selection_score": score,
                "selection_score_components": components,
                "direction": "UNKNOWN",
                "entry_concept": "NONE",
                "exit_concept": "NONE",
                "edge_claimed": False,
                "forward_outcomes_used": False,
                "locked_outcomes_accessed": False,
                "next_action": "GOVERNED_DEVELOPMENT_OUTCOME_TEST_ONLY_AFTER_FREEZE",
            })
            accepted.append(row)

        accepted.sort(key=lambda c: (-float(c["selection_score"]), -int(c.get("distinct_session_support", 0)), str(c.get("center_state"))))
        selected = accepted[: args.max_candidates]
        cap_rejections = [
            {
                "community_id": c.get("community_id"),
                "candidate_id": c.get("candidate_id"),
                "center_state": c.get("center_state"),
                "reason": "MAX_CANDIDATES_CAP",
                "selection_score": c.get("selection_score"),
            }
            for c in accepted[args.max_candidates :]
        ]
        all_rejections = rejected + cap_rejections

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in selected), encoding="utf-8")
        rejections_path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in all_rejections), encoding="utf-8")

        status = "TRANSITION_COMMUNITY_CANDIDATES_SELECTED" if selected else "NO_DISTINCT_TRANSITION_COMMUNITY_CANDIDATES"
        result.update({
            "status": status,
            "communities_read": len(communities),
            "communities_sha256": sha256(communities_path),
            "candidate_path": str(output_path),
            "candidate_sha256": sha256(output_path),
            "rejections_path": str(rejections_path),
            "rejections_sha256": sha256(rejections_path),
            "selected_candidates": len(selected),
            "accepted_before_cap": len(accepted),
            "rejected_candidates": len(all_rejections),
            "selection_policy": {
                "high_information_states": sorted(HIGH_INFORMATION_STATES),
                "generic_center_states_rejected": sorted(GENERIC_CENTER_STATES),
                "max_session_fraction": args.max_session_fraction,
                "min_episode_support": args.min_episode_support,
                "min_session_support": args.min_session_support,
                "max_episode_presence": args.max_episode_presence,
                "min_supported_edges": args.min_supported_edges,
                "max_supported_edges": args.max_supported_edges,
                "max_candidates": args.max_candidates,
            },
            "search_pressure": {
                "communities_read": len(communities),
                "accepted_before_cap": len(accepted),
                "selected_candidates": len(selected),
                "rejected_candidates": len(all_rejections),
            },
            "next_action": "COMPILE_OR_DEVELOPMENT_TEST_ONLY_AFTER_GOVERNED_REVIEW" if selected else "NO_TRANSITION_COMMUNITY_CANDIDATES",
            "interpretation": "Pre-outcome selector for high-information transition communities. Ubiquitous/generic state neighborhoods are rejected before any outcome test. No return, excursion, profitability, or edge label is computed.",
        })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"TRANSITION_COMMUNITY_CANDIDATES_SELECTED", "NO_DISTINCT_TRANSITION_COMMUNITY_CANDIDATES"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
