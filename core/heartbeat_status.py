from __future__ import annotations

from typing import Mapping


def top_blockers_from_counts(
    counts: Mapping[str, int] | None,
    *,
    limit: int = 5,
) -> list[dict]:
    ranked = sorted(
        (
            {"reason": str(reason), "count": int(count)}
            for reason, count in dict(counts or {}).items()
            if str(reason).strip() and int(count) > 0
        ),
        key=lambda row: (-int(row["count"]), str(row["reason"])),
    )
    return ranked[: max(1, int(limit))]


def derive_cycle_semantics(
    *,
    market_mode: str | None,
    market_open: bool,
    suggestion_count: int,
    blocker_counts: Mapping[str, int] | None = None,
    last_error: str | None = None,
) -> dict:
    normalized_market_open = bool(market_open)
    normalized_market_mode = "OFFHOURS" if not normalized_market_open else str(market_mode or "").strip().upper()
    normalized_suggestion_count = max(0, int(suggestion_count or 0))
    normalized_last_error = str(last_error or "").strip()
    top_blockers = top_blockers_from_counts(blocker_counts)
    if normalized_last_error:
        return {
            "semantic_state": "error",
            "dominant_reason": "cycle_error",
            "subreason": normalized_last_error,
            "primary_blocker": normalized_last_error,
            "market_mode": normalized_market_mode,
            "market_open": normalized_market_open,
            "top_blockers": top_blockers,
        }
    if not normalized_market_open:
        return {
            "semantic_state": "market_closed",
            "dominant_reason": "MARKET_CLOSED",
            "subreason": "",
            "primary_blocker": "MARKET_CLOSED",
            "market_mode": normalized_market_mode,
            "market_open": False,
            "top_blockers": top_blockers,
        }
    if normalized_suggestion_count > 0:
        return {
            "semantic_state": "ok",
            "dominant_reason": "suggestions_generated",
            "subreason": "",
            "primary_blocker": None,
            "market_mode": normalized_market_mode,
            "market_open": True,
            "top_blockers": top_blockers,
        }
    if top_blockers:
        top_reason = str((top_blockers[0] or {}).get("reason") or "").strip()
        return {
            "semantic_state": "blocked",
            "dominant_reason": "candidates_blocked",
            "subreason": top_reason,
            "primary_blocker": top_reason or None,
            "market_mode": normalized_market_mode,
            "market_open": True,
            "top_blockers": top_blockers,
        }
    return {
        "semantic_state": "no_candidates",
        "dominant_reason": "no_candidates",
        "subreason": "",
        "primary_blocker": "NO_CANDIDATES",
        "market_mode": normalized_market_mode,
        "market_open": True,
        "top_blockers": top_blockers,
    }
