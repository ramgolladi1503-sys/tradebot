from __future__ import annotations

from typing import Any, Mapping

from core.feed_truth_state import FeedTruthStateDecision, LIVE, normalize_feed_truth_state

FEED_EXECUTION_TRUTH_SCHEMA_VERSION = 1


def feed_truth_allows_live_selection(
    value: FeedTruthStateDecision | Mapping[str, Any] | str | None,
) -> bool:
    if isinstance(value, FeedTruthStateDecision):
        return bool(value.strict_live)
    if isinstance(value, Mapping):
        if "feed_truth_allows_live_selection" in value:
            return bool(value.get("feed_truth_allows_live_selection"))
        return normalize_feed_truth_state(value.get("feed_truth_state") or value.get("state")) == LIVE
    return normalize_feed_truth_state(value) == LIVE


def attach_feed_execution_truth(payload: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(payload or {})
    allowed = feed_truth_allows_live_selection(out)
    out["feed_truth_allows_live_selection"] = allowed
    out["feed_truth_allows_executable_candidates"] = allowed
    out["feed_execution_truth_schema_version"] = FEED_EXECUTION_TRUTH_SCHEMA_VERSION
    return out


__all__ = [
    "FEED_EXECUTION_TRUTH_SCHEMA_VERSION",
    "attach_feed_execution_truth",
    "feed_truth_allows_live_selection",
]
