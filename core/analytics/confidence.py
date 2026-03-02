from __future__ import annotations


def should_emit_suggestion(sample_size: int, effect_size: float, sessions: int) -> bool:
    try:
        n = int(sample_size)
    except Exception:
        n = 0
    try:
        eff = float(effect_size)
    except Exception:
        eff = 0.0
    try:
        sess = int(sessions)
    except Exception:
        sess = 0

    if n < 30:
        return False
    if abs(eff) < 0.15:
        return False
    if sess < 2:
        return False
    return True
