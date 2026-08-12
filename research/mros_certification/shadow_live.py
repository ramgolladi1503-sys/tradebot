"""Read-only shadow-session validation; historical data is never live proof."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping


def validate_shadow_session(session: Mapping[str, object], *, candidate_sha: str) -> dict[str, object]:
    if session.get("candidate_sha") != candidate_sha:
        raise ValueError("SHADOW_CANDIDATE_SHA_MISMATCH")
    if session.get("source_kind") != "genuine_live" or session.get("replay", False) or session.get("synthetic", False):
        return {"status": "BLOCKED_LIVE_WINDOW", "reason": "GENUINE_LIVE_SESSION_REQUIRED", "candidate_sha": candidate_sha}
    if session.get("broker_write_authority") or session.get("order_authority") or session.get("paper_authorized") or session.get("live_authorized"):
        raise ValueError("SHADOW_AUTHORITY_FORBIDDEN")
    observed = session.get("observed_at")
    if not isinstance(observed, str):
        raise ValueError("SHADOW_TIMESTAMP_REQUIRED")
    datetime.fromisoformat(observed.replace("Z", "+00:00")).astimezone(timezone.utc)
    return {"status": "SHADOW_LIVE_VALID", "candidate_sha": candidate_sha, "read_only": True, "is_order_action": False}
