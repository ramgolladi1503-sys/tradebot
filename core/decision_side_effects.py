from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from config import config as cfg
from core.decision_dag import Decision, MarketSnapshot, NODE_N8_STRATEGY_SELECT
from core.time_utils import now_ist


def _blocked_candidates_path() -> Path:
    desk_log_dir = getattr(cfg, "DESK_LOG_DIR", None)
    if desk_log_dir:
        return Path(str(desk_log_dir)) / "blocked_candidates.jsonl"
    desk = getattr(cfg, "DESK_ID", "DEFAULT")
    return Path(f"logs/desks/{desk}/blocked_candidates.jsonl")


def _is_potentially_eligible(candidate_summary: Mapping[str, Any]) -> bool:
    family = candidate_summary.get("family")
    allowed = candidate_summary.get("allowed")
    return bool(family) or bool(allowed)


def handle_post_decision_side_effects(
    decision: Decision,
    explain: Sequence[Mapping[str, Any]],
    snapshot: MarketSnapshot,
) -> None:
    """
    Handle post-decision side effects only from already-computed DAG outputs.
    This function must not recompute gate logic.
    """
    if decision.allowed:
        return

    n8_row = None
    for row in explain:
        if str(row.get("node") or "") == NODE_N8_STRATEGY_SELECT:
            n8_row = row
            break
    if not isinstance(n8_row, Mapping):
        return

    n8_facts = n8_row.get("facts") or {}
    if not isinstance(n8_facts, Mapping):
        return
    candidate_summary = n8_facts.get("candidate_summary") or {}
    if not isinstance(candidate_summary, Mapping):
        return
    if not _is_potentially_eligible(candidate_summary):
        return

    precondition_failures = n8_facts.get("precondition_failures") or []
    failure_nodes = set()
    if isinstance(precondition_failures, Sequence) and not isinstance(precondition_failures, (str, bytes, bytearray)):
        for node in precondition_failures:
            node_s = str(node or "").strip()
            if node_s:
                failure_nodes.add(node_s)

    explain_snippet = []
    for row in explain:
        if not isinstance(row, Mapping):
            continue
        node = str(row.get("node") or "")
        if failure_nodes and node not in failure_nodes:
            continue
        if (not failure_nodes) and bool(row.get("ok", True)):
            continue
        reasons = row.get("reasons") or []
        if not isinstance(reasons, Sequence) or isinstance(reasons, (str, bytes, bytearray)):
            reasons = []
        explain_snippet.append(
            {
                "node": node,
                "ok": bool(row.get("ok", False)),
                "reasons": [str(r) for r in reasons if str(r).strip()],
            }
        )

    blockers = [str(x) for x in (decision.blockers or ()) if str(x).strip()]
    primary_blocker = str(decision.primary_blocker or (blockers[0] if blockers else "UNKNOWN_BLOCKER"))
    record = {
        "ts_ist": now_ist().isoformat(),
        "ts_epoch": float(snapshot.ts_epoch),
        "symbol": snapshot.symbol,
        "stage": "decision_dag",
        "reason_code": primary_blocker,
        "reason": primary_blocker,
        "reason_text": "strategy_candidate_blocked_by_preconditions",
        "candidate_summary": dict(candidate_summary),
        "primary_blocker": primary_blocker,
        "blockers": blockers,
        "node_explain_snippet": explain_snippet,
    }

    try:
        path = _blocked_candidates_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        # Side-effect logging must not affect decision flow.
        return
