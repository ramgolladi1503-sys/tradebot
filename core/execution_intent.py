from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict
import time


@dataclass(frozen=True)
class ExecutionIntent:
    intent_id: str
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    target: float
    qty: int
    rank_score: float
    opportunity_score: float
    final_action: str
    execution_status: str
    decision_ts_epoch: float


def _get(candidate: Any, key: str, default=None):
    if isinstance(candidate, dict):
        return candidate.get(key, default)
    return getattr(candidate, key, default)


def build_execution_intent(candidate: Any) -> ExecutionIntent | None:
    if not bool(_get(candidate, "selected_for_execution", False)):
        return None

    entry = _get(candidate, "execution_entry")
    if entry is None:
        return None

    try:
        return ExecutionIntent(
            intent_id=str(_get(candidate, "trade_id") or f"intent_{int(time.time()*1000)}"),
            trade_id=str(_get(candidate, "trade_id") or ""),
            symbol=str(_get(candidate, "symbol") or ""),
            direction=str(_get(candidate, "direction") or ""),
            entry_price=float(entry),
            stop_loss=float(_get(candidate, "stop_loss") or 0.0),
            target=float(_get(candidate, "target") or 0.0),
            qty=int(_get(candidate, "qty") or 0),
            rank_score=float(_get(candidate, "rank_score") or 0.0),
            opportunity_score=float(_get(candidate, "opportunity_score") or 0.0),
            final_action=str(_get(candidate, "final_action") or "EXECUTE"),
            execution_status=str(_get(candidate, "execution_entry_status") or "unknown"),
            decision_ts_epoch=float(time.time()),
        )
    except Exception:
        return None


def attach_execution_intent(candidate: Any) -> Any:
    intent = build_execution_intent(candidate)
    if intent is None:
        return candidate

    if isinstance(candidate, dict):
        out = dict(candidate)
        out["execution_intent"] = asdict(intent)
        out["phase2_frozen"] = True
        return out

    # dataclass fallback
    try:
        setattr(candidate, "execution_intent", asdict(intent))
        setattr(candidate, "phase2_frozen", True)
    except Exception:
        pass
    return candidate


def clear_execution_intent(candidate: Any) -> Any:
    if isinstance(candidate, dict):
        candidate.pop("execution_intent", None)
        candidate["phase2_frozen"] = False
        return candidate

    try:
        setattr(candidate, "execution_intent", None)
        setattr(candidate, "phase2_frozen", False)
    except Exception:
        pass
    return candidate
