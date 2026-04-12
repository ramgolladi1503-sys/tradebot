from __future__ import annotations

from typing import Any


def exit_policy(candidate: dict[str, Any]) -> dict[str, Any]:
    thesis = str(candidate.get("thesis_type") or "unknown")
    if thesis == "breakout_continuation":
        return {"type": "trail", "trail_pct": 0.25, "fail_fast": True}
    if thesis == "reclaim_continuation":
        return {"type": "level_loss", "level": "reclaim", "fail_fast": True}
    if thesis == "rejection_reversal":
        return {"type": "quick_target", "rr": 1.2}
    if thesis in {"mean_reversion_bounce", "mean_reversion_fade"}:
        return {"type": "fixed_target", "rr": 1.5}
    if thesis == "trend_pullback":
        return {"type": "trail", "trail_pct": 0.35}
    return {"type": "unknown"}


def annotate_exit(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    out["exit_policy"] = exit_policy(out)
    return out
