from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from core.execution_decision_contract import infer_execution_decision
from core.orchestrator_truth import is_reportable_executable_candidate


@dataclass(frozen=True)
class ShadowCycleRow:
    index: int
    trade_id: str | None
    legacy_allowed: bool
    shadow_allowed: bool
    shadow_state: str
    primary_reason: str
    matched: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "trade_id": self.trade_id,
            "legacy_allowed": self.legacy_allowed,
            "shadow_allowed": self.shadow_allowed,
            "shadow_state": self.shadow_state,
            "primary_reason": self.primary_reason,
            "matched": self.matched,
        }


def _value(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def compare_cycle(candidates: Iterable[Any]) -> dict[str, Any]:
    rows: list[ShadowCycleRow] = []
    for index, candidate in enumerate(candidates):
        legacy_allowed = bool(is_reportable_executable_candidate(candidate))
        decision = infer_execution_decision(candidate)
        rows.append(
            ShadowCycleRow(
                index=index,
                trade_id=_value(candidate, "trade_id"),
                legacy_allowed=legacy_allowed,
                shadow_allowed=decision.allowed,
                shadow_state=decision.state.value,
                primary_reason=decision.primary_reason,
                matched=legacy_allowed == decision.allowed,
            )
        )
    mismatch_rows = [row for row in rows if not row.matched]
    return {
        "row_count": len(rows),
        "match_count": len(rows) - len(mismatch_rows),
        "mismatch_count": len(mismatch_rows),
        "parity_rate": 1.0 if not rows else (len(rows) - len(mismatch_rows)) / len(rows),
        "shadow_states": dict(Counter(row.shadow_state for row in rows)),
        "mismatch_reasons": dict(Counter(row.primary_reason for row in mismatch_rows)),
        "rows": [row.to_dict() for row in rows],
    }


__all__ = ["ShadowCycleRow", "compare_cycle"]
