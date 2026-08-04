from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping


_ALLOWED_SIDES = {"BUY", "SELL", "BOTH"}
_ALLOWED_BASES = {"BUY_TURNOVER", "SELL_TURNOVER", "TOTAL_TURNOVER", "BROKERAGE", "ACCUMULATED_COMPONENTS"}


def _finite_nonnegative(value: float, *, name: str) -> float:
    out = float(value)
    if not math.isfinite(out) or out < 0:
        raise ValueError(f"{name}_invalid")
    return out


@dataclass(frozen=True)
class CostRule:
    name: str
    kind: str
    side: str
    base: str
    value: float
    component_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("cost_rule_name_missing")
        kind = self.kind.strip().upper()
        side = self.side.strip().upper()
        base = self.base.strip().upper()
        if kind not in {"RATE", "FLAT_PER_ORDER"}:
            raise ValueError(f"unsupported_cost_rule_kind={kind}")
        if side not in _ALLOWED_SIDES:
            raise ValueError(f"unsupported_cost_rule_side={side}")
        if base not in _ALLOWED_BASES:
            raise ValueError(f"unsupported_cost_rule_base={base}")
        value = _finite_nonnegative(self.value, name=f"cost_rule_{self.name}")
        if base == "ACCUMULATED_COMPONENTS" and not self.component_names:
            raise ValueError("accumulated_components_requires_names")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "base", base)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "component_names", tuple(self.component_names))


@dataclass(frozen=True)
class CostSchedule:
    schedule_id: str
    version: str
    effective_from: date
    effective_until: date | None
    rules: tuple[CostRule, ...]

    def __post_init__(self) -> None:
        if not self.schedule_id.strip() or not self.version.strip():
            raise ValueError("cost_schedule_identity_missing")
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise ValueError("cost_schedule_date_range_invalid")
        names = [rule.name for rule in self.rules]
        if len(names) != len(set(names)):
            raise ValueError("duplicate_cost_rule_name")

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "CostSchedule":
        rules_payload = payload.get("rules")
        if not isinstance(rules_payload, list) or not rules_payload:
            raise ValueError("cost_schedule_rules_missing")
        rules = []
        for item in rules_payload:
            if not isinstance(item, Mapping):
                raise ValueError("cost_rule_not_object")
            rules.append(CostRule(
                name=str(item.get("name") or ""), kind=str(item.get("kind") or ""),
                side=str(item.get("side") or "BOTH"), base=str(item.get("base") or ""),
                value=float(item.get("value") or 0.0),
                component_names=tuple(str(value) for value in (item.get("component_names") or ())),
            ))
        until_raw = str(payload.get("effective_until") or "").strip()
        return cls(
            schedule_id=str(payload.get("schedule_id") or ""),
            version=str(payload.get("version") or ""),
            effective_from=date.fromisoformat(str(payload.get("effective_from") or "")),
            effective_until=date.fromisoformat(until_raw) if until_raw else None,
            rules=tuple(rules),
        )

    @classmethod
    def from_json_file(cls, path: str | Path) -> "CostSchedule":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("cost_schedule_not_object")
        return cls.from_mapping(payload)

    def is_effective(self, trade_date: date) -> bool:
        return trade_date >= self.effective_from and (self.effective_until is None or trade_date <= self.effective_until)


@dataclass(frozen=True)
class TradeCostInput:
    trade_date: date
    buy_turnover: float
    sell_turnover: float
    buy_order_count: int
    sell_order_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "buy_turnover", _finite_nonnegative(self.buy_turnover, name="buy_turnover"))
        object.__setattr__(self, "sell_turnover", _finite_nonnegative(self.sell_turnover, name="sell_turnover"))
        if self.buy_order_count < 0 or self.sell_order_count < 0:
            raise ValueError("order_count_negative")


@dataclass(frozen=True)
class TradeCostResult:
    schedule_id: str
    schedule_version: str
    components: dict[str, float]
    total_cost: float

    def to_record(self) -> dict[str, object]:
        return {"schedule_id": self.schedule_id, "schedule_version": self.schedule_version, "components": dict(self.components), "total_cost": self.total_cost}


def _side_order_count(rule: CostRule, trade: TradeCostInput) -> int:
    if rule.side == "BUY": return trade.buy_order_count
    if rule.side == "SELL": return trade.sell_order_count
    return trade.buy_order_count + trade.sell_order_count


def _base_value(rule: CostRule, trade: TradeCostInput, components: Mapping[str, float]) -> float:
    if rule.base == "BUY_TURNOVER": return trade.buy_turnover if rule.side in {"BUY", "BOTH"} else 0.0
    if rule.base == "SELL_TURNOVER": return trade.sell_turnover if rule.side in {"SELL", "BOTH"} else 0.0
    if rule.base == "TOTAL_TURNOVER":
        if rule.side == "BUY": return trade.buy_turnover
        if rule.side == "SELL": return trade.sell_turnover
        return trade.buy_turnover + trade.sell_turnover
    if rule.base == "BROKERAGE": return components.get("brokerage", 0.0)
    if rule.base == "ACCUMULATED_COMPONENTS":
        missing = [name for name in rule.component_names if name not in components]
        if missing:
            raise ValueError(f"cost_rule_dependency_missing={','.join(missing)}")
        return sum(components[name] for name in rule.component_names)
    raise ValueError(f"unsupported_cost_rule_base={rule.base}")


def calculate_trade_costs(schedule: CostSchedule, trade: TradeCostInput) -> TradeCostResult:
    if not schedule.is_effective(trade.trade_date):
        raise ValueError("cost_schedule_not_effective_for_trade_date")
    components: dict[str, float] = {}
    for rule in schedule.rules:
        value = rule.value * _side_order_count(rule, trade) if rule.kind == "FLAT_PER_ORDER" else rule.value * _base_value(rule, trade, components)
        components[rule.name] = _finite_nonnegative(value, name=f"cost_component_{rule.name}")
    return TradeCostResult(schedule.schedule_id, schedule.version, components, sum(components.values()))


def select_effective_schedule(schedules: Iterable[CostSchedule], *, trade_date: date) -> CostSchedule:
    matching = [schedule for schedule in schedules if schedule.is_effective(trade_date)]
    if not matching:
        raise ValueError("no_effective_cost_schedule")
    matching.sort(key=lambda item: (item.effective_from, item.version))
    latest = matching[-1]
    same_start = [item for item in matching if item.effective_from == latest.effective_from]
    if len({item.version for item in same_start}) > 1:
        raise ValueError("ambiguous_effective_cost_schedule")
    return latest
