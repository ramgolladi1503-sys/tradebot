from __future__ import annotations

from typing import Any


def top_reason_codes(candidate: dict[str, Any], limit: int = 3) -> list[str]:
    codes = list(candidate.get("phase2_reason_codes") or candidate.get("reason_codes") or [])
    if codes:
        return [str(x) for x in codes[:limit]]
    reasons = []
    for key in ("reject_reason", "reason", "execution_block_reason"):
        text = str(candidate.get(key) or "").strip()
        if text:
            reasons.append(text)
    for key in ("phase2_soft_penalties", "gate_reasons", "blockers"):
        for value in list(candidate.get(key) or []):
            text = str(value or "").strip()
            if text:
                reasons.append(text)
    out = []
    seen = set()
    for item in reasons:
        norm = item.lower()
        if norm in seen:
            continue
        seen.add(norm)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def build_reason_string(candidate: dict[str, Any]) -> str:
    state = str(candidate.get("phase2_trust_bucket") or candidate.get("decision") or "candidate").upper()
    thesis = str(candidate.get("thesis_type") or "unknown")
    reasons = top_reason_codes(candidate, limit=3)
    if reasons:
        return f"{state}: thesis={thesis}; reasons=" + ", ".join(reasons)
    return f"{state}: thesis={thesis}; reasons=none"


def annotate_explainability(candidate: dict[str, Any]) -> dict[str, Any]:
    out = dict(candidate)
    out["phase2_reason_string"] = build_reason_string(out)
    return out
