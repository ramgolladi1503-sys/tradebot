"""Compact, truthful operator status for Morning Readiness V1."""
from __future__ import annotations

from typing import Any, Mapping


def build_status(*, state: str, release_sha: str, session_id: str | None = None, underlying: str = "MISSING", option: str = "MISSING", depth: str = "MISSING", persistence: str = "FAILED", memory: str = "FAILED", cas: str = "BLOCKED", decision_plane: str = "BLOCKED", blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": "MROS_STATUS",
        "state": state,
        "release_sha": release_sha,
        "session_id": session_id,
        "underlying_feed": underlying,
        "option_feed": option,
        "depth_feed": depth,
        "persistence": persistence,
        "memory": memory,
        "cas": cas,
        "decision_plane": decision_plane,
        "blockers": list(blockers or []),
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "orders_placed": 0,
        "orders_modified": 0,
        "orders_cancelled": 0,
    }
