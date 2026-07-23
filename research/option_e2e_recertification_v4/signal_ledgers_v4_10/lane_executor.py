from __future__ import annotations


def execute_lane(entry: dict[str, object], artifact: dict[str, object]) -> dict[str, object]:
    blockers = list(artifact.get("certification_blockers", []) or [])
    if not blockers and artifact.get("blocker"):
        blockers = [str(artifact["blocker"])]
    if not blockers:
        blockers = list(entry.get("certification_blockers", []) or [])
    data_fetch_status = str(artifact.get("data_fetch_status") or entry.get("data_fetch_status") or "UNKNOWN")
    if not blockers:
        blockers = ["EXACT_BLOCKER_NOT_PRESENT"]
    return {
        "status": "SOURCE_BLOCKED",
        "strategy_id": entry.get("strategy_id"),
        "data_fetch_status": data_fetch_status,
        "blockers": blockers,
        "reason": "lane-specific evidence shows no certifiable historical option truth",
        "execution_allowed": False,
        "broker_api_called": False,
        "is_order_action": False,
        "allowed_for_live_execution": False,
        "read_only": True,
    }
