from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from config import config as cfg
from core.ablation import evaluate_ablation_sanity, load_latest_ablation_metrics
from core.incidents import SEV3, create_incident
from core.walk_forward import load_latest_walk_forward_summary, promotion_metrics_from_summary


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


@dataclass
class RetrainTriggerResult:
    retrain_required: bool
    reason_codes: list[str]
    metrics: dict[str, float]
    incident_id: str | None = None


@dataclass
class PromotionGateResult:
    allowed: bool
    reason_code: str
    details: dict[str, Any]


class RetrainManager:
    def __init__(self) -> None:
        self.window = int(getattr(cfg, "ML_RETRAIN_ROLLING_WINDOW", 20))
        self.min_win_rate = float(getattr(cfg, "ML_RETRAIN_MIN_WIN_RATE", 0.45))
        self.max_drawdown = float(getattr(cfg, "ML_RETRAIN_MAX_ROLLING_DRAWDOWN", -0.06))
        self.min_expectancy = float(getattr(cfg, "ML_RETRAIN_MIN_EXPECTANCY", 0.0))
        self.min_return_delta = float(getattr(cfg, "ML_PROMOTION_MIN_RETURN_DELTA", 0.0))
        self.max_drawdown_worsen = float(getattr(cfg, "ML_PROMOTION_MAX_DRAWDOWN_WORSEN", 0.0))
        self.require_ablation = bool(getattr(cfg, "ML_PROMOTION_REQUIRE_ABLATION_SAFETY", True))

    def _rolling_metrics(self, live_df: pd.DataFrame) -> tuple[dict[str, float], list[str]]:
        if live_df is None or live_df.empty:
            return {}, ["RETRAIN_DATA_MISSING"]
        if "actual" not in live_df.columns or "pnl" not in live_df.columns:
            return {}, ["RETRAIN_DATA_MISSING_FIELDS"]
        window = max(1, int(self.window))
        if len(live_df) < window:
            return {}, [f"RETRAIN_DATA_INSUFFICIENT:{len(live_df)}<{window}"]
        tail = live_df.tail(window).copy()
        tail["actual"] = pd.to_numeric(tail["actual"], errors="coerce")
        tail["pnl"] = pd.to_numeric(tail["pnl"], errors="coerce")
        tail = tail.dropna(subset=["actual", "pnl"])
        if tail.empty:
            return {}, ["RETRAIN_DATA_INVALID"]

        win_rate = float((tail["actual"] > 0).mean())
        expectancy = float(tail["pnl"].mean())
        equity_curve = tail["pnl"].cumsum()
        rolling_peak = equity_curve.cummax()
        drawdown_series = equity_curve - rolling_peak
        max_drawdown = float(drawdown_series.min()) if not drawdown_series.empty else 0.0
        start_equity = abs(float(equity_curve.iloc[0])) if not equity_curve.empty else 0.0
        scale = start_equity if start_equity > 1e-6 else max(abs(float(equity_curve).max()), 1.0)
        max_drawdown_pct = max_drawdown / float(scale)

        return {
            "rolling_win_rate": win_rate,
            "rolling_expectancy": expectancy,
            "rolling_drawdown_pct": max_drawdown_pct,
            "window_size": float(len(tail)),
        }, []

    def evaluate_retrain_trigger(
        self,
        live_df: pd.DataFrame,
        *,
        emit_incident: bool = True,
    ) -> RetrainTriggerResult:
        metrics, precheck_reasons = self._rolling_metrics(live_df)
        if precheck_reasons:
            return RetrainTriggerResult(
                retrain_required=False,
                reason_codes=precheck_reasons,
                metrics=metrics,
                incident_id=None,
            )

        reasons: list[str] = []
        if metrics.get("rolling_win_rate", 1.0) < self.min_win_rate:
            reasons.append("RETRAIN_TRIGGER:ROLLING_WIN_RATE_LOW")
        if metrics.get("rolling_expectancy", 0.0) < self.min_expectancy:
            reasons.append("RETRAIN_TRIGGER:NEGATIVE_EXPECTANCY")
        if metrics.get("rolling_drawdown_pct", 0.0) <= self.max_drawdown:
            reasons.append("RETRAIN_TRIGGER:ROLLING_DRAWDOWN_BREACH")

        retrain_required = bool(reasons)
        incident_id = None
        if retrain_required and emit_incident:
            incident_id = create_incident(
                SEV3,
                "MODEL_RETRAIN_TRIGGER",
                {
                    "reason_codes": reasons,
                    "metrics": metrics,
                },
            )
        return RetrainTriggerResult(
            retrain_required=retrain_required,
            reason_codes=reasons if reasons else ["RETRAIN_TRIGGER:NOT_REQUIRED"],
            metrics=metrics,
            incident_id=incident_id,
        )

    def evaluate_promotion_gate(
        self,
        champion_metrics: dict[str, Any],
        challenger_metrics: dict[str, Any],
        *,
        walk_forward_metrics: dict[str, Any] | None = None,
        ablation_report: dict[str, Any] | None = None,
    ) -> PromotionGateResult:
        wf_metrics = walk_forward_metrics
        wf_reason = None
        if wf_metrics is None:
            summary, load_reason = load_latest_walk_forward_summary()
            if load_reason:
                wf_reason = load_reason
                wf_metrics = {}
            else:
                wf_metrics, wf_reason = promotion_metrics_from_summary(summary)
        wf_metrics = dict(wf_metrics or {})

        if wf_reason:
            return PromotionGateResult(
                allowed=False,
                reason_code=f"MODEL_PROMOTE_REJECT:{wf_reason.upper()}",
                details={"walk_forward_reason": wf_reason, "walk_forward_metrics": wf_metrics},
            )

        if ablation_report is None:
            ablation_report, ablation_reason = load_latest_ablation_metrics()
            if ablation_reason and self.require_ablation:
                return PromotionGateResult(
                    allowed=False,
                    reason_code=f"MODEL_PROMOTE_REJECT:{ablation_reason.upper()}",
                    details={"ablation_reason": ablation_reason},
                )
        ok_ablation, ablation_reasons = evaluate_ablation_sanity(ablation_report)
        if self.require_ablation and not ok_ablation:
            code = ablation_reasons[0] if ablation_reasons else "ABLATION_SANITY_FAIL"
            return PromotionGateResult(
                allowed=False,
                reason_code=f"MODEL_PROMOTE_REJECT:{code.upper()}",
                details={"ablation_reasons": ablation_reasons},
            )

        champ_return = _to_float(
            wf_metrics.get("champion_return", champion_metrics.get("return", champion_metrics.get("acc"))),
            default=0.0,
        )
        chall_return = _to_float(
            wf_metrics.get("challenger_return", challenger_metrics.get("return", challenger_metrics.get("acc"))),
            default=0.0,
        )
        champ_dd = _to_float(
            wf_metrics.get("champion_max_drawdown", champion_metrics.get("max_drawdown", 0.0)),
            default=0.0,
        )
        chall_dd = _to_float(
            wf_metrics.get("challenger_max_drawdown", challenger_metrics.get("max_drawdown", 0.0)),
            default=0.0,
        )

        return_delta = chall_return - champ_return
        if return_delta < self.min_return_delta:
            return PromotionGateResult(
                allowed=False,
                reason_code="MODEL_PROMOTE_REJECT:WALK_FORWARD_RETURN_NOT_IMPROVED",
                details={
                    "champion_return": champ_return,
                    "challenger_return": chall_return,
                    "required_delta": self.min_return_delta,
                },
            )

        drawdown_worsen = chall_dd - champ_dd
        if drawdown_worsen < -abs(self.max_drawdown_worsen):
            return PromotionGateResult(
                allowed=False,
                reason_code="MODEL_PROMOTE_REJECT:WALK_FORWARD_DRAWDOWN_WORSE",
                details={
                    "champion_max_drawdown": champ_dd,
                    "challenger_max_drawdown": chall_dd,
                    "max_allowed_worsen": self.max_drawdown_worsen,
                },
            )

        return PromotionGateResult(
            allowed=True,
            reason_code="MODEL_PROMOTE_OK",
            details={
                "champion_return": champ_return,
                "challenger_return": chall_return,
                "champion_max_drawdown": champ_dd,
                "challenger_max_drawdown": chall_dd,
                "return_delta": return_delta,
                "drawdown_worsen": drawdown_worsen,
            },
        )

