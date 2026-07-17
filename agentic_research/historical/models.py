from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HistoricalCampaignConfig:
    symbol: str = "NIFTY_F1"
    timezone: str = "Asia/Kolkata"
    round_trip_cost_bps: float = 2.0
    adverse_cost_bps: float = 5.0
    severe_cost_bps: float = 10.0
    target_rr: float = 1.5
    stop_atr_buffer: float = 0.10
    max_hold_bars: int = 15
    minimum_sessions: int = 80
    minimum_total_trades: int = 30
    minimum_holdout_trades: int = 10
    minimum_holdout_profit_factor: float = 1.10
    minimum_positive_wfa_fraction: float = 0.60
    maximum_top_five_session_positive_share: float = 0.70
    train_sessions: int = 80
    validation_sessions: int = 20
    step_sessions: int = 20
    holdout_fraction: float = 0.20
    boundary_purge_sessions: int = 1


class HistoricalCampaignError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_returns(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "trades": 0,
            "net_expectancy_bps": None,
            "net_pnl_bps": 0.0,
            "profit_factor": None,
            "win_rate": None,
            "wins": 0,
            "losses": 0,
        }
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (
        math.inf
        if gross_loss == 0 and gross_win > 0
        else (gross_win / gross_loss if gross_loss else None)
    )
    return {
        "trades": len(values),
        "net_expectancy_bps": sum(values) / len(values),
        "net_pnl_bps": sum(values),
        "profit_factor": profit_factor,
        "win_rate": len(wins) / len(values),
        "wins": len(wins),
        "losses": len(losses),
    }
