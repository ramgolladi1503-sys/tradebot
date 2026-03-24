from __future__ import annotations

from typing import Iterable


def soft_signal(
    *,
    reason: str,
    direction: str,
    setup_type: str,
    regime_path: str | None = None,
    base_score: float = 0.05,
    soft_flags: Iterable[str] | None = None,
) -> dict:
    flags = [str(flag) for flag in (soft_flags or []) if str(flag)]
    if reason and reason not in flags:
        flags.append(str(reason))
    if "soft_reject" not in flags:
        flags.append("soft_reject")
    return {
        "direction": direction,
        "reason": str(reason),
        "score": round(float(base_score), 3),
        "soft_flags": flags,
        "setup_type": setup_type,
        "regime_path": regime_path,
        "soft_reject": True,
        "advisory_only": True,
    }
