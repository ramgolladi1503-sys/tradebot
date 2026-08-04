from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping


def _finite(value: float, *, name: str) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name}_not_finite")
    return out


@dataclass(frozen=True)
class ContractOutcome:
    candidate_id: str
    contract_id: str
    role: str
    gross_pnl: float
    transaction_cost: float
    fillable_quantity: float
    requested_quantity: float
    evidence_ref: str

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.contract_id.strip() or not self.role.strip():
            raise ValueError("contract_outcome_identity_missing")
        if not self.evidence_ref.strip():
            raise ValueError("contract_outcome_evidence_missing")
        for name in ("gross_pnl", "transaction_cost", "fillable_quantity", "requested_quantity"):
            object.__setattr__(self, name, _finite(getattr(self, name), name=name))
        if self.transaction_cost < 0 or self.fillable_quantity < 0 or self.requested_quantity <= 0:
            raise ValueError("contract_outcome_quantities_invalid")
        if self.fillable_quantity > self.requested_quantity:
            raise ValueError("fillable_quantity_exceeds_requested")

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.transaction_cost

    @property
    def fill_ratio(self) -> float:
        return self.fillable_quantity / self.requested_quantity


@dataclass(frozen=True)
class CounterfactualComparison:
    candidate_id: str
    selected_contract_id: str | None
    selected_net_pnl: float | None
    best_observed_contract_id: str
    best_observed_net_pnl: float
    selected_opportunity_cost: float | None
    rejected_candidate_net_pnl: float | None
    outcomes: tuple[ContractOutcome, ...]

    def to_record(self) -> dict[str, object]:
        return {"candidate_id": self.candidate_id, "selected_contract_id": self.selected_contract_id, "selected_net_pnl": self.selected_net_pnl, "best_observed_contract_id": self.best_observed_contract_id, "best_observed_net_pnl": self.best_observed_net_pnl, "selected_opportunity_cost": self.selected_opportunity_cost, "rejected_candidate_net_pnl": self.rejected_candidate_net_pnl, "outcomes": [{"contract_id": row.contract_id, "role": row.role, "gross_pnl": row.gross_pnl, "transaction_cost": row.transaction_cost, "net_pnl": row.net_pnl, "fill_ratio": row.fill_ratio, "evidence_ref": row.evidence_ref} for row in self.outcomes]}


def compare_contract_counterfactuals(outcomes: Iterable[ContractOutcome], *, selected_contract_id: str | None, candidate_was_rejected: bool) -> CounterfactualComparison:
    rows = tuple(outcomes)
    if not rows:
        raise ValueError("counterfactual_outcomes_empty")
    candidate_ids = {row.candidate_id for row in rows}
    if len(candidate_ids) != 1:
        raise ValueError("counterfactual_candidate_mismatch")
    contract_ids = [row.contract_id for row in rows]
    if len(contract_ids) != len(set(contract_ids)):
        raise ValueError("duplicate_contract_outcome")
    best = max(rows, key=lambda row: (row.net_pnl, row.fill_ratio, row.contract_id))
    selected = None
    if selected_contract_id is not None:
        selected = next((row for row in rows if row.contract_id == selected_contract_id), None)
        if selected is None:
            raise ValueError("selected_contract_outcome_missing")
    rejected_net = None
    if candidate_was_rejected:
        if selected is not None:
            raise ValueError("rejected_candidate_must_not_have_selected_contract")
        role_rows = [row for row in rows if row.role.strip().upper() == "PROPOSED"]
        if len(role_rows) != 1:
            raise ValueError("rejected_candidate_requires_one_proposed_outcome")
        rejected_net = role_rows[0].net_pnl
    return CounterfactualComparison(rows[0].candidate_id, selected.contract_id if selected else None, selected.net_pnl if selected else None, best.contract_id, best.net_pnl, (best.net_pnl - selected.net_pnl) if selected else None, rejected_net, tuple(sorted(rows, key=lambda row: row.contract_id)))


def blocker_value(decisions: Iterable[Mapping[str, object]]) -> dict[str, dict[str, float | int]]:
    aggregated: dict[str, dict[str, float | int]] = {}
    for row in decisions:
        blocker = str(row.get("blocker") or "").strip()
        if not blocker:
            raise ValueError("blocker_missing")
        if not bool(row.get("was_blocked")):
            continue
        pnl = _finite(float(row.get("counterfactual_net_pnl")), name="counterfactual_net_pnl")
        bucket = aggregated.setdefault(blocker, {"blocked_count": 0, "profits_missed": 0.0, "losses_avoided": 0.0, "net_value_of_blocker": 0.0})
        bucket["blocked_count"] = int(bucket["blocked_count"]) + 1
        if pnl > 0:
            bucket["profits_missed"] = float(bucket["profits_missed"]) + pnl
            bucket["net_value_of_blocker"] = float(bucket["net_value_of_blocker"]) - pnl
        elif pnl < 0:
            avoided = abs(pnl)
            bucket["losses_avoided"] = float(bucket["losses_avoided"]) + avoided
            bucket["net_value_of_blocker"] = float(bucket["net_value_of_blocker"]) + avoided
    return aggregated
