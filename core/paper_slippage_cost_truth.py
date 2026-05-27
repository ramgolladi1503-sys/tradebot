"""Read-only paper slippage and cost truth for EDGE-86.

This module consumes EDGE-84 reduced paper outcomes and derives net paper PnL
after explicit slippage and transaction-cost assumptions. It does not mutate the
paper journal, append events, call adapters, change runtime behavior, or make
strategy lifecycle decisions.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from core.paper_outcome_reducer import OUTCOME_CLOSED, PaperOutcomeReductionReport

PAPER_SLIPPAGE_COST_SCHEMA_VERSION = 1
PAPER_SLIPPAGE_COST_SOURCE = "paper_slippage_cost_truth_v1"

SLIPPAGE_COST_STATUS_REDUCED = "PAPER_SLIPPAGE_COST_REDUCED"
SLIPPAGE_COST_STATUS_BLOCKED = "PAPER_SLIPPAGE_COST_BLOCKED"

UNKNOWN_REGIME = "UNKNOWN"
UNKNOWN_STRATEGY = "UNKNOWN_STRATEGY"

INVALID_OUTCOME_REPORT_REASON = "invalid_outcome_reduction_report"
INVALID_COST_MODEL_REASON = "invalid_cost_model"
NO_CLOSED_OUTCOMES_REASON = "no_closed_paper_outcomes"
MISSING_PRICE_OR_QUANTITY_REASON = "missing_price_or_quantity"
MISSING_GROSS_PNL_REASON = "missing_gross_pnl"

_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


@dataclass(frozen=True)
class PaperSlippageCostModel:
    """Deterministic paper cost model used to convert gross PnL into net PnL."""

    entry_slippage_per_unit: float = 0.0
    exit_slippage_per_unit: float = 0.0
    fee_per_order: float = 0.0
    fee_rate: float = 0.0
    fixed_cost_per_trade: float = 0.0
    tax_rate: float = 0.0

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "entry_slippage_per_unit": self.entry_slippage_per_unit,
            "exit_slippage_per_unit": self.exit_slippage_per_unit,
            "fee_per_order": self.fee_per_order,
            "fee_rate": self.fee_rate,
            "fixed_cost_per_trade": self.fixed_cost_per_trade,
            "tax_rate": self.tax_rate,
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class PaperSlippageCostCandidate:
    """Net-cost truth for one closed paper candidate."""

    candidate_id: str
    strategy_id: str
    symbol: str
    regime: str
    quantity: float
    entry_price: float | None
    exit_price: float | None
    gross_pnl: float | None
    turnover: float
    entry_slippage_cost: float
    exit_slippage_cost: float
    fee_cost: float
    tax_cost: float
    fixed_cost: float
    total_cost: float
    net_pnl: float | None
    cost_to_gross_ratio: float | None
    blockers: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "candidate_id": self.candidate_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "regime": self.regime,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "gross_pnl": self.gross_pnl,
            "turnover": self.turnover,
            "entry_slippage_cost": self.entry_slippage_cost,
            "exit_slippage_cost": self.exit_slippage_cost,
            "fee_cost": self.fee_cost,
            "tax_cost": self.tax_cost,
            "fixed_cost": self.fixed_cost,
            "total_cost": self.total_cost,
            "net_pnl": self.net_pnl,
            "cost_to_gross_ratio": self.cost_to_gross_ratio,
            "blockers": list(self.blockers),
            "metadata": dict(self.metadata),
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class PaperSlippageCostBucket:
    """Aggregated net-cost truth for one strategy/regime bucket."""

    strategy_id: str
    regime: str
    closed_count: int
    net_win_count: int
    net_loss_count: int
    net_flat_count: int
    total_gross_pnl: float
    total_slippage_cost: float
    total_fee_cost: float
    total_tax_cost: float
    total_fixed_cost: float
    total_cost: float
    total_net_pnl: float
    average_net_pnl: float
    net_win_rate: float
    net_loss_rate: float
    net_expectancy_per_trade: float
    cost_drag_per_trade: float
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "strategy_id": self.strategy_id,
            "regime": self.regime,
            "closed_count": self.closed_count,
            "net_win_count": self.net_win_count,
            "net_loss_count": self.net_loss_count,
            "net_flat_count": self.net_flat_count,
            "total_gross_pnl": self.total_gross_pnl,
            "total_slippage_cost": self.total_slippage_cost,
            "total_fee_cost": self.total_fee_cost,
            "total_tax_cost": self.total_tax_cost,
            "total_fixed_cost": self.total_fixed_cost,
            "total_cost": self.total_cost,
            "total_net_pnl": self.total_net_pnl,
            "average_net_pnl": self.average_net_pnl,
            "net_win_rate": self.net_win_rate,
            "net_loss_rate": self.net_loss_rate,
            "net_expectancy_per_trade": self.net_expectancy_per_trade,
            "cost_drag_per_trade": self.cost_drag_per_trade,
            "metadata": dict(self.metadata),
            "read_only": True,
            "append": False,
        }
        _mark_non_action(payload)
        return payload


@dataclass(frozen=True)
class PaperSlippageCostReport:
    """Read-only report converting gross paper outcomes into net-cost truth."""

    schema_version: int
    source: str
    status: str
    reason_code: str
    reasons: tuple[str, ...]
    outcome_report_valid: bool
    closed_outcome_count: int
    candidate_count: int
    valid_candidate_count: int
    blocked_candidate_count: int
    bucket_count: int
    cost_model: PaperSlippageCostModel
    candidates: tuple[PaperSlippageCostCandidate, ...]
    buckets: tuple[PaperSlippageCostBucket, ...]
    read_only: bool = True
    append: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_order_action(self) -> bool:
        return False

    @property
    def broker_api_called(self) -> bool:
        return False

    @property
    def live_order_action(self) -> bool:
        return False

    @property
    def broker_order_action(self) -> bool:
        return False

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source": self.source,
            "status": self.status,
            "reason_code": self.reason_code,
            "reasons": list(self.reasons),
            "outcome_report_valid": self.outcome_report_valid,
            "closed_outcome_count": self.closed_outcome_count,
            "candidate_count": self.candidate_count,
            "valid_candidate_count": self.valid_candidate_count,
            "blocked_candidate_count": self.blocked_candidate_count,
            "bucket_count": self.bucket_count,
            "cost_model": self.cost_model.to_payload(),
            "candidates": [candidate.to_payload() for candidate in self.candidates],
            "buckets": [bucket.to_payload() for bucket in self.buckets],
            "read_only": self.read_only,
            "append": self.append,
            "metadata": dict(self.metadata),
        }
        _mark_non_action(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), sort_keys=True, default=str)


def build_slippage_cost_truth(
    outcome_report: PaperOutcomeReductionReport | Mapping[str, Any],
    *,
    entry_slippage_per_unit: Any = 0.0,
    exit_slippage_per_unit: Any = 0.0,
    fee_per_order: Any = 0.0,
    fee_rate: Any = 0.0,
    fixed_cost_per_trade: Any = 0.0,
    tax_rate: Any = 0.0,
) -> PaperSlippageCostReport:
    """Build deterministic net-cost truth from closed EDGE-84 paper outcomes."""

    model, model_reasons = _cost_model(
        entry_slippage_per_unit=entry_slippage_per_unit,
        exit_slippage_per_unit=exit_slippage_per_unit,
        fee_per_order=fee_per_order,
        fee_rate=fee_rate,
        fixed_cost_per_trade=fixed_cost_per_trade,
        tax_rate=tax_rate,
    )
    if model_reasons:
        return _blocked_report(
            reason_code=INVALID_COST_MODEL_REASON,
            reasons=model_reasons,
            cost_model=model,
            metadata={"blocked_before_outcome_reduction": True},
        )

    report_payload = _payload(outcome_report)
    if not _outcome_report_valid(report_payload):
        return _blocked_report(
            reason_code=INVALID_OUTCOME_REPORT_REASON,
            reasons=(INVALID_OUTCOME_REPORT_REASON,),
            cost_model=model,
        )

    raw_outcomes = report_payload.get("outcomes") or []
    closed = [_payload(item) for item in raw_outcomes if _text(_payload(item).get("status")) == OUTCOME_CLOSED]
    if not closed:
        return _blocked_report(
            reason_code=NO_CLOSED_OUTCOMES_REASON,
            reasons=(NO_CLOSED_OUTCOMES_REASON,),
            outcome_report_valid=True,
            cost_model=model,
        )

    candidates = tuple(_candidate_from_outcome(outcome, model) for outcome in closed)
    candidate_reasons = _dedupe(reason for candidate in candidates for reason in candidate.blockers)
    valid_candidates = tuple(candidate for candidate in candidates if not candidate.blockers and candidate.net_pnl is not None)
    buckets = tuple(_bucket_from_group(key, items) for key, items in _group_candidates(valid_candidates))
    status = SLIPPAGE_COST_STATUS_BLOCKED if candidate_reasons else SLIPPAGE_COST_STATUS_REDUCED
    reason_code = candidate_reasons[0] if candidate_reasons else "ok"
    return PaperSlippageCostReport(
        schema_version=PAPER_SLIPPAGE_COST_SCHEMA_VERSION,
        source=PAPER_SLIPPAGE_COST_SOURCE,
        status=status,
        reason_code=reason_code,
        reasons=candidate_reasons,
        outcome_report_valid=True,
        closed_outcome_count=len(closed),
        candidate_count=len(candidates),
        valid_candidate_count=len(valid_candidates),
        blocked_candidate_count=len(candidates) - len(valid_candidates),
        bucket_count=len(buckets),
        cost_model=model,
        candidates=candidates,
        buckets=buckets,
        metadata={
            "derived_from": str(report_payload.get("source") or "paper_outcome_reducer"),
            "gross_pnl_source": "paper_outcome_reducer",
            "net_pnl_formula": "gross_pnl_minus_total_cost",
            "read_only_reducer": True,
        },
    )


def _candidate_from_outcome(
    outcome: Mapping[str, Any],
    model: PaperSlippageCostModel,
) -> PaperSlippageCostCandidate:
    quantity = _positive_float_or_none(outcome.get("quantity"))
    entry_price = _positive_float_or_none(outcome.get("entry_price"))
    exit_price = _positive_float_or_none(outcome.get("exit_price"))
    gross_pnl = _finite_float_or_none(outcome.get("gross_pnl"))
    blockers: list[str] = []
    if quantity is None or entry_price is None or exit_price is None:
        blockers.append(MISSING_PRICE_OR_QUANTITY_REASON)
    if gross_pnl is None:
        blockers.append(MISSING_GROSS_PNL_REASON)

    if blockers:
        return PaperSlippageCostCandidate(
            candidate_id=_text(outcome.get("candidate_id")),
            strategy_id=_text(outcome.get("strategy_id")) or UNKNOWN_STRATEGY,
            symbol=_text(outcome.get("symbol")),
            regime=_regime_from_outcome(outcome),
            quantity=0.0 if quantity is None else quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            gross_pnl=gross_pnl,
            turnover=0.0,
            entry_slippage_cost=0.0,
            exit_slippage_cost=0.0,
            fee_cost=0.0,
            tax_cost=0.0,
            fixed_cost=0.0,
            total_cost=0.0,
            net_pnl=None,
            cost_to_gross_ratio=None,
            blockers=_dedupe(blockers),
            metadata={"cost_truth_blocked": True},
        )

    assert quantity is not None
    assert entry_price is not None
    assert exit_price is not None
    assert gross_pnl is not None
    turnover = _round(quantity * (abs(entry_price) + abs(exit_price)))
    entry_slippage_cost = _round(quantity * model.entry_slippage_per_unit)
    exit_slippage_cost = _round(quantity * model.exit_slippage_per_unit)
    fee_cost = _round((2.0 * model.fee_per_order) + (turnover * model.fee_rate))
    tax_cost = _round(turnover * model.tax_rate)
    fixed_cost = _round(model.fixed_cost_per_trade)
    total_cost = _round(entry_slippage_cost + exit_slippage_cost + fee_cost + tax_cost + fixed_cost)
    net_pnl = _round(gross_pnl - total_cost)
    ratio = _round(total_cost / abs(gross_pnl)) if gross_pnl != 0.0 else None
    return PaperSlippageCostCandidate(
        candidate_id=_text(outcome.get("candidate_id")),
        strategy_id=_text(outcome.get("strategy_id")) or UNKNOWN_STRATEGY,
        symbol=_text(outcome.get("symbol")),
        regime=_regime_from_outcome(outcome),
        quantity=quantity,
        entry_price=entry_price,
        exit_price=exit_price,
        gross_pnl=gross_pnl,
        turnover=turnover,
        entry_slippage_cost=entry_slippage_cost,
        exit_slippage_cost=exit_slippage_cost,
        fee_cost=fee_cost,
        tax_cost=tax_cost,
        fixed_cost=fixed_cost,
        total_cost=total_cost,
        net_pnl=net_pnl,
        cost_to_gross_ratio=ratio,
        metadata={"cost_truth_blocked": False},
    )


def _bucket_from_group(
    key: tuple[str, str],
    candidates: tuple[PaperSlippageCostCandidate, ...],
) -> PaperSlippageCostBucket:
    strategy_id, regime = key
    closed_count = len(candidates)
    net_values = [float(candidate.net_pnl or 0.0) for candidate in candidates]
    total_gross = _round(sum(candidate.gross_pnl or 0.0 for candidate in candidates))
    total_entry_slippage = _round(sum(candidate.entry_slippage_cost for candidate in candidates))
    total_exit_slippage = _round(sum(candidate.exit_slippage_cost for candidate in candidates))
    total_slippage = _round(total_entry_slippage + total_exit_slippage)
    total_fee = _round(sum(candidate.fee_cost for candidate in candidates))
    total_tax = _round(sum(candidate.tax_cost for candidate in candidates))
    total_fixed = _round(sum(candidate.fixed_cost for candidate in candidates))
    total_cost = _round(sum(candidate.total_cost for candidate in candidates))
    total_net = _round(sum(net_values))
    win_count = sum(1 for value in net_values if value > 0.0)
    loss_count = sum(1 for value in net_values if value < 0.0)
    flat_count = closed_count - win_count - loss_count
    return PaperSlippageCostBucket(
        strategy_id=strategy_id,
        regime=regime,
        closed_count=closed_count,
        net_win_count=win_count,
        net_loss_count=loss_count,
        net_flat_count=flat_count,
        total_gross_pnl=total_gross,
        total_slippage_cost=total_slippage,
        total_fee_cost=total_fee,
        total_tax_cost=total_tax,
        total_fixed_cost=total_fixed,
        total_cost=total_cost,
        total_net_pnl=total_net,
        average_net_pnl=_round(total_net / closed_count) if closed_count else 0.0,
        net_win_rate=_round(win_count / closed_count) if closed_count else 0.0,
        net_loss_rate=_round(loss_count / closed_count) if closed_count else 0.0,
        net_expectancy_per_trade=_round(total_net / closed_count) if closed_count else 0.0,
        cost_drag_per_trade=_round(total_cost / closed_count) if closed_count else 0.0,
        metadata={"gross_to_net_cost_truth": True},
    )


def _group_candidates(
    candidates: tuple[PaperSlippageCostCandidate, ...]
) -> tuple[tuple[tuple[str, str], tuple[PaperSlippageCostCandidate, ...]], ...]:
    grouped: dict[tuple[str, str], list[PaperSlippageCostCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault((candidate.strategy_id, candidate.regime), []).append(candidate)
    return tuple(
        (key, tuple(items))
        for key, items in sorted(grouped.items(), key=lambda item: item[0])
    )


def _cost_model(
    *,
    entry_slippage_per_unit: Any,
    exit_slippage_per_unit: Any,
    fee_per_order: Any,
    fee_rate: Any,
    fixed_cost_per_trade: Any,
    tax_rate: Any,
) -> tuple[PaperSlippageCostModel, tuple[str, ...]]:
    raw = {
        "entry_slippage_per_unit": entry_slippage_per_unit,
        "exit_slippage_per_unit": exit_slippage_per_unit,
        "fee_per_order": fee_per_order,
        "fee_rate": fee_rate,
        "fixed_cost_per_trade": fixed_cost_per_trade,
        "tax_rate": tax_rate,
    }
    parsed: dict[str, float] = {}
    reasons: list[str] = []
    for key, value in raw.items():
        parsed_value = _finite_float_or_none(value)
        if parsed_value is None or parsed_value < 0.0:
            reasons.append(f"{INVALID_COST_MODEL_REASON}:{key}")
            parsed_value = 0.0
        parsed[key] = parsed_value
    return PaperSlippageCostModel(**parsed), _dedupe(reasons)


def _outcome_report_valid(payload: Mapping[str, Any]) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("journal_valid") is not True:
        return False
    if payload.get("read_only") is not True:
        return False
    if payload.get("append") is not False:
        return False
    if not isinstance(payload.get("outcomes"), list):
        return False
    return True


def _blocked_report(
    *,
    reason_code: str,
    reasons: tuple[str, ...],
    cost_model: PaperSlippageCostModel,
    outcome_report_valid: bool = False,
    metadata: dict[str, Any] | None = None,
) -> PaperSlippageCostReport:
    return PaperSlippageCostReport(
        schema_version=PAPER_SLIPPAGE_COST_SCHEMA_VERSION,
        source=PAPER_SLIPPAGE_COST_SOURCE,
        status=SLIPPAGE_COST_STATUS_BLOCKED,
        reason_code=reason_code,
        reasons=_dedupe(reasons),
        outcome_report_valid=outcome_report_valid,
        closed_outcome_count=0,
        candidate_count=0,
        valid_candidate_count=0,
        blocked_candidate_count=0,
        bucket_count=0,
        cost_model=cost_model,
        candidates=(),
        buckets=(),
        metadata=dict(metadata or {}),
    )


def _payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_payload"):
        value = value.to_payload()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _regime_from_outcome(outcome: Mapping[str, Any]) -> str:
    metadata = outcome.get("metadata") if isinstance(outcome.get("metadata"), Mapping) else {}
    for key in ("regime", "market_regime", "regime_id"):
        value = _text(metadata.get(key) if isinstance(metadata, Mapping) else None) or _text(outcome.get(key))
        if value:
            return value
    return UNKNOWN_REGIME


def _positive_float_or_none(value: Any) -> float | None:
    parsed = _finite_float_or_none(value)
    if parsed is None or parsed <= 0.0:
        return None
    return parsed


def _finite_float_or_none(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _text(value: Any) -> str:
    return str(value or "").strip()


def _round(value: float) -> float:
    return round(float(value), 10)


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value or "").strip()}))


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "INVALID_COST_MODEL_REASON",
    "INVALID_OUTCOME_REPORT_REASON",
    "MISSING_GROSS_PNL_REASON",
    "MISSING_PRICE_OR_QUANTITY_REASON",
    "NO_CLOSED_OUTCOMES_REASON",
    "PAPER_SLIPPAGE_COST_SCHEMA_VERSION",
    "PAPER_SLIPPAGE_COST_SOURCE",
    "PaperSlippageCostBucket",
    "PaperSlippageCostCandidate",
    "PaperSlippageCostModel",
    "PaperSlippageCostReport",
    "SLIPPAGE_COST_STATUS_BLOCKED",
    "SLIPPAGE_COST_STATUS_REDUCED",
    "UNKNOWN_REGIME",
    "UNKNOWN_STRATEGY",
    "build_slippage_cost_truth",
]
