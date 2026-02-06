from __future__ import annotations

from typing import Any, Dict, List


def features_from_row(row: Dict[str, Any]) -> List[float]:
    score = float(row.get("score_0_100") or 0.0) / 100.0
    reg = row.get("regime_probs") or {}
    reg_max = max(reg.values()) if reg else 0.0
    shock = float(row.get("shock_score") or 0.0)
    spread = float(row.get("spread_pct") or 0.0)
    depth = float(row.get("depth_imbalance") or 0.0)
    drawdown = float(row.get("drawdown_pct") or 0.0)
    loss_streak = float(row.get("loss_streak") or 0.0)
    open_risk = float(row.get("open_risk") or 0.0)
    delta = float(row.get("delta_exposure") or 0.0)
    gamma = float(row.get("gamma_exposure") or 0.0)
    vega = float(row.get("vega_exposure") or 0.0)
    return [
        score, reg_max, shock, spread, depth, drawdown,
        loss_streak, open_risk, delta, gamma, vega
    ]
