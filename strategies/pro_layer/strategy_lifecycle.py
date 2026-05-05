from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from strategies.pro_layer.alpha_validation import AlphaValidationReport, validate_alpha_edge

STATE_ORDER = ["DISABLED", "SHADOW", "PAPER", "PILOT", "LIVE"]


@dataclass(frozen=True)
class StrategyLifecycleDecision:
    strategy: str
    current_state: str
    next_state: str
    action: str
    alpha_status: str
    reasons: list[str]
    report: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm_state(value: Any) -> str:
    text = str(value or "SHADOW").strip().upper()
    return text if text in STATE_ORDER else "SHADOW"


def _promote_one(state: str) -> str:
    state = _norm_state(state)
    if state == "DISABLED":
        return "SHADOW"
    idx = STATE_ORDER.index(state)
    return STATE_ORDER[min(len(STATE_ORDER) - 1, idx + 1)]


def _demote_one(state: str) -> str:
    state = _norm_state(state)
    idx = STATE_ORDER.index(state)
    return STATE_ORDER[max(0, idx - 1)]


def decide_strategy_lifecycle(
    rows: list[dict[str, Any]],
    *,
    strategy: str,
    current_state: str = "SHADOW",
    min_trades: int = 30,
) -> StrategyLifecycleDecision:
    state = _norm_state(current_state)
    report: AlphaValidationReport = validate_alpha_edge(rows, strategy=strategy, min_trades=min_trades)
    reasons = list(report.reasons)
    if report.status == "PROMOTE":
        next_state = _promote_one(state)
        action = "PROMOTE_ONE_STEP" if next_state != state else "KEEP_LIVE"
    elif report.status == "INSUFFICIENT_DATA":
        next_state = state if state in {"SHADOW", "PAPER"} else _demote_one(state)
        action = "KEEP_COLLECTING" if next_state == state else "DEMOTE_INSUFFICIENT_DATA"
    else:
        next_state = _demote_one(state)
        action = "DEMOTE"
        if state == "SHADOW":
            next_state = "DISABLED"
            action = "DISABLE"
    return StrategyLifecycleDecision(
        strategy=strategy,
        current_state=state,
        next_state=next_state,
        action=action,
        alpha_status=report.status,
        reasons=reasons,
        report=report.as_dict(),
    )
