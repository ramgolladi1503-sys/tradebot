from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.paths import logs_dir
from core.strategy_tracker import StrategyTracker


def _safe_float(value: Any) -> float:
    try:
        if value in (None, "", "None"):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


@dataclass(frozen=True)
class StrategyLearningDecision:
    strategy_family: str
    allowed: bool
    size_multiplier: float
    state: str
    reason: str
    metrics: dict[str, Any]


class PaperStrategyLearningEngine:
    def __init__(self, *, state_path: str | None = None) -> None:
        self.tracker = StrategyTracker(max_len=300)
        self.state_path = Path(state_path) if state_path else (logs_dir() / "paper_strategy_learning.json")
        try:
            if self.state_path.exists():
                self.tracker.load(self.state_path)
        except Exception:
            pass

    def record_trade_outcome(
        self,
        *,
        strategy_family: str,
        pnl: float,
        execution_quality: float | None = None,
        symbol: str | None = None,
    ) -> None:
        family = str(strategy_family or "unknown").strip().lower() or "unknown"
        self.tracker.record(family, float(_safe_float(pnl)))
        if symbol:
            self.tracker.record_symbol(str(symbol).strip().upper(), float(_safe_float(pnl)))
        if execution_quality is not None:
            self.tracker.record_execution_quality(family, float(_safe_float(execution_quality)))
        self._save()

    def decision(self, strategy_family: str) -> StrategyLearningDecision:
        family = str(strategy_family or "unknown").strip().lower() or "unknown"
        stats = dict(self.tracker.stats.get(family, {}) or {})
        trades = int(stats.get("trades", 0) or 0)
        win_rate = float(self.tracker.win_rate(family) if trades else 1.0)
        profit_factor_raw = stats.get("profit_factor", 1.0)
        profit_factor = 9.99 if profit_factor_raw == "inf" else float(_safe_float(profit_factor_raw))
        sharpe = stats.get("sharpe")
        sharpe_value = float(_safe_float(sharpe)) if sharpe is not None else 0.0
        exec_quality = float(_safe_float(stats.get("exec_quality_avg")))
        utility = float(_safe_float(stats.get("utility")))

        if self.tracker.is_quarantined(family):
            return StrategyLearningDecision(
                strategy_family=family,
                allowed=False,
                size_multiplier=0.0,
                state="QUARANTINE",
                reason="tracker_quarantined",
                metrics=self._metrics_payload(family, stats, win_rate),
            )

        if trades < 10:
            return StrategyLearningDecision(
                strategy_family=family,
                allowed=True,
                size_multiplier=0.75,
                state="LEARNING",
                reason="insufficient_sample",
                metrics=self._metrics_payload(family, stats, win_rate),
            )

        if win_rate < 0.40 or (profit_factor > 0 and profit_factor < 0.90):
            return StrategyLearningDecision(
                strategy_family=family,
                allowed=False,
                size_multiplier=0.0,
                state="BLOCKED",
                reason="weak_performance",
                metrics=self._metrics_payload(family, stats, win_rate),
            )

        size_multiplier = 1.0
        state = "NORMAL"
        reason = "stable"

        if trades >= 20 and win_rate >= 0.58 and profit_factor >= 1.20 and sharpe_value >= 0.10:
            size_multiplier = 1.10
            state = "PROMOTED"
            reason = "strong_performance"
        elif win_rate < 0.48 or profit_factor < 1.00 or utility < 0:
            size_multiplier = 0.65
            state = "DOWNSIZED"
            reason = "mixed_performance"
        elif exec_quality and exec_quality < 0.45:
            size_multiplier = 0.75
            state = "CAUTION"
            reason = "weak_execution_quality"

        return StrategyLearningDecision(
            strategy_family=family,
            allowed=True,
            size_multiplier=float(max(0.25, min(1.25, size_multiplier))),
            state=state,
            reason=reason,
            metrics=self._metrics_payload(family, stats, win_rate),
        )

    def _metrics_payload(self, family: str, stats: dict[str, Any], win_rate: float) -> dict[str, Any]:
        payload = dict(stats or {})
        payload.update(
            {
                "strategy_family": family,
                "win_rate": round(float(win_rate), 4),
                "is_quarantined": bool(self.tracker.is_quarantined(family)),
                "is_decaying": bool(self.tracker.is_decaying(family)),
            }
        )
        return payload

    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.tracker.save(self.state_path)
        except Exception:
            pass
