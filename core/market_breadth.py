from __future__ import annotations

from typing import Any


def breadth_score(context: dict[str, Any]) -> float:
    adv = float(context.get("advancers", 0))
    dec = float(context.get("decliners", 0))
    total = adv + dec
    if total <= 0:
        return 0.5
    ratio = adv / total
    if ratio > 0.65:
        return 0.7
    if ratio < 0.35:
        return 0.3
    return 0.5


def annotate_breadth(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    ctx = candidate.get("breadth_context", {})
    out["breadth_score"] = breadth_score(ctx)
    return out
