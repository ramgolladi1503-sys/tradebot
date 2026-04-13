from __future__ import annotations

from typing import Dict, Any, List, Tuple


def _safe(v):
    try:
        return float(v)
    except Exception:
        return None


def normalize_profile(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = raw or {}
    return {
        "vah": _safe(raw.get("vah")),
        "val": _safe(raw.get("val")),
        "poc": _safe(raw.get("poc")),
        "hvns": list(raw.get("hvns") or []),
        "lvns": list(raw.get("lvns") or []),
    }


def downside_path_quality(profile: Dict[str, Any], entry: float, stop: float) -> Tuple[float, float]:
    """Returns (path_score, target_price)."""
    poc = profile.get("poc")
    if poc is None:
        return 0.3, entry

    risk = abs(stop - entry)
    reward = abs(entry - poc)
    rr = reward / max(risk, 1e-6)

    # crude LVN bonus: if any lvn between entry and poc
    lvn_bonus = 0.0
    for node in profile.get("lvns") or []:
        p = _safe(node.get("price") if isinstance(node, dict) else None)
        if p and min(entry, poc) <= p <= max(entry, poc):
            lvn_bonus = 0.2
            break

    score = min(1.0, (rr / 3.0)) + lvn_bonus
    return min(score, 1.0), poc
