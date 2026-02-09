from __future__ import annotations

import json
from pathlib import Path


def compute_multiplier(
    base: float,
    drawdown_pct: float,
    vol_proxy: float,
    exec_quality: float,
    decay_prob: float,
    regime_entropy: float,
) -> float:
    mult = base
    if drawdown_pct < -0.02:
        mult *= 0.7
    if vol_proxy > 1.0:
        mult *= 0.8
    if exec_quality < 0.5:
        mult *= 0.7
    if decay_prob > 0.7:
        mult *= 0.6
    if regime_entropy > 1.3:
        mult *= 0.8
    return max(0.1, min(1.0, mult))


def write_status(path: Path, payload: dict) -> Path:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return path
