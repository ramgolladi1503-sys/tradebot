"""Canonical Strategy Family Architecture Contract.

Formalizes:
- StrategyFamily: Top-level canonical strategy families (TREND, MEAN_REVERT, DEFINED_RISK, SCALP_ONLY, NO_TRADE).
- StrategySubfamily: Optional granular execution subfamilies (BREAKOUT, CONTINUATION, PULLBACK, RANGE_WATCHLIST, EXHAUSTION, EVENT_EXPANSION).
- StrategyFamilyContract: Governed validation, alias normalization, and serialization.
- check_strategy_family_compatibility: Explicit pre-admission compatibility gate.

Guarantees:
- Zero order authority (is_order_action=False, broker_write_authority=False).
- Regime selects eligible families; strategy owns immutable identity; candidate inherits identity.
- No layer silently rewrites another layer's ontology.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Final, FrozenSet, Iterable


class StrategyFamily(str, enum.Enum):
    """Top-level canonical strategy families."""

    TREND = "TREND"
    MEAN_REVERT = "MEAN_REVERT"
    DEFINED_RISK = "DEFINED_RISK"
    SCALP_ONLY = "SCALP_ONLY"
    NO_TRADE = "NO_TRADE"

    @classmethod
    def from_str(cls, value: str | StrategyFamily | None) -> StrategyFamily | None:
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        raw = str(value).strip().upper().replace("-", "_").replace(" ", "_")
        aliases: dict[str, StrategyFamily] = {
            "TREND": cls.TREND,
            "TRENDING": cls.TREND,
            "TREND_CONTINUATION": cls.TREND,
            "DIRECTIONAL": cls.TREND,
            "BREAKOUT": cls.TREND,
            "CONTINUATION": cls.TREND,
            "PULLBACK": cls.TREND,
            "MEAN_REVERT": cls.MEAN_REVERT,
            "MEAN_REVERSION": cls.MEAN_REVERT,
            "REVERSAL": cls.MEAN_REVERT,
            "RANGE": cls.MEAN_REVERT,
            "RANGE_WATCHLIST": cls.MEAN_REVERT,
            "DEFINED_RISK": cls.DEFINED_RISK,
            "EVENT": cls.DEFINED_RISK,
            "EVENT_VOLATILITY": cls.DEFINED_RISK,
            "SCALP_ONLY": cls.SCALP_ONLY,
            "SCALP": cls.SCALP_ONLY,
            "NO_TRADE": cls.NO_TRADE,
            "NONE": cls.NO_TRADE,
        }
        return aliases.get(raw)


class StrategySubfamily(str, enum.Enum):
    """Optional granular execution subfamilies."""

    BREAKOUT = "BREAKOUT"
    CONTINUATION = "CONTINUATION"
    PULLBACK = "PULLBACK"
    RANGE_WATCHLIST = "RANGE_WATCHLIST"
    EXHAUSTION = "EXHAUSTION"
    EVENT_EXPANSION = "EVENT_EXPANSION"
    MOMENTUM_IMPULSE = "MOMENTUM_IMPULSE"
    OVERNIGHT_TREND = "OVERNIGHT_TREND"

    @classmethod
    def from_str(cls, value: str | StrategySubfamily | None) -> StrategySubfamily | None:
        if value is None:
            return None
        if isinstance(value, cls):
            return value
        raw = str(value).strip().upper().replace("-", "_").replace(" ", "_")
        aliases: dict[str, StrategySubfamily] = {
            "BREAKOUT": cls.BREAKOUT,
            "CONTINUATION": cls.CONTINUATION,
            "PULLBACK": cls.PULLBACK,
            "RANGE_WATCHLIST": cls.RANGE_WATCHLIST,
            "EXHAUSTION": cls.EXHAUSTION,
            "EVENT_EXPANSION": cls.EVENT_EXPANSION,
            "MOMENTUM_IMPULSE": cls.MOMENTUM_IMPULSE,
            "OVERNIGHT_TREND": cls.OVERNIGHT_TREND,
        }
        return aliases.get(raw)


@dataclass(frozen=True)
class StrategyDefinition:
    """Immutable registered strategy metadata."""

    strategy_id: str
    strategy_family: StrategyFamily
    strategy_subfamily: StrategySubfamily | None = None
    description: str = ""
    is_order_action: bool = False
    broker_write_authority: bool = False
    paper_authorized: bool = False
    live_authorized: bool = False

    def __post_init__(self) -> None:
        if not str(self.strategy_id).strip():
            raise ValueError("strategy_id_required")
        if not isinstance(self.strategy_family, StrategyFamily):
            raise ValueError(f"invalid_strategy_family:{self.strategy_family}")
        if self.is_order_action:
            raise ValueError("strategy_definition_order_action_forbidden")
        if self.broker_write_authority:
            raise ValueError("strategy_definition_broker_write_forbidden")
        if self.paper_authorized:
            raise ValueError("strategy_definition_paper_forbidden")
        if self.live_authorized:
            raise ValueError("strategy_definition_live_forbidden")

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_family": self.strategy_family.value,
            "strategy_subfamily": (
                self.strategy_subfamily.value if self.strategy_subfamily else None
            ),
            "description": self.description,
            "is_order_action": False,
            "broker_write_authority": False,
        }


@dataclass(frozen=True)
class FamilyCompatibilityResult:
    """Result of evaluating candidate strategy family against regime eligibility."""

    compatible: bool
    candidate_family: StrategyFamily | None
    allowed_families: FrozenSet[StrategyFamily]
    reason_code: str
    is_order_action: bool = False
    broker_write_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "candidate_family": self.candidate_family.value if self.candidate_family else None,
            "allowed_families": [f.value for f in sorted(self.allowed_families, key=lambda x: x.value)],
            "reason_code": self.reason_code,
            "is_order_action": False,
            "broker_write_authority": False,
        }


def check_strategy_family_compatibility(
    candidate_family: StrategyFamily | str | None,
    allowed_strategy_families: Iterable[StrategyFamily | str] | None,
) -> FamilyCompatibilityResult:
    """Pre-admission compatibility gate: candidate.strategy_family in allowed_strategy_families.

    Fails closed on missing, unknown, or empty families.
    Never rewrites the candidate's family identity.
    """
    resolved_candidate_family: StrategyFamily | None = None
    if isinstance(candidate_family, StrategyFamily):
        resolved_candidate_family = candidate_family
    elif candidate_family is not None:
        resolved_candidate_family = StrategyFamily.from_str(candidate_family)

    if resolved_candidate_family is None:
        return FamilyCompatibilityResult(
            compatible=False,
            candidate_family=None,
            allowed_families=frozenset(),
            reason_code="FAMILY_MISSING" if candidate_family is None else "FAMILY_UNKNOWN",
        )

    resolved_allowed: set[StrategyFamily] = set()
    if allowed_strategy_families:
        for f in allowed_strategy_families:
            resolved_f = f if isinstance(f, StrategyFamily) else StrategyFamily.from_str(f)
            if resolved_f is not None:
                resolved_allowed.add(resolved_f)

    allowed_set: FrozenSet[StrategyFamily] = frozenset(resolved_allowed)

    if not allowed_set:
        return FamilyCompatibilityResult(
            compatible=False,
            candidate_family=resolved_candidate_family,
            allowed_families=allowed_set,
            reason_code="REGIME_FAMILY_SET_EMPTY",
        )

    if resolved_candidate_family in allowed_set:
        return FamilyCompatibilityResult(
            compatible=True,
            candidate_family=resolved_candidate_family,
            allowed_families=allowed_set,
            reason_code="FAMILY_COMPATIBLE",
        )

    return FamilyCompatibilityResult(
        compatible=False,
        candidate_family=resolved_candidate_family,
        allowed_families=allowed_set,
        reason_code="FAMILY_MISMATCH",
    )


# -----------------------------------------------------------------------------
# Canonical Strategy Registry
# -----------------------------------------------------------------------------
STRATEGY_REGISTRY: Final[dict[str, StrategyDefinition]] = {
    # Frozen C1 & C2
    "C1_INTRADAY_15M_IMPULSE": StrategyDefinition(
        strategy_id="C1_INTRADAY_15M_IMPULSE",
        strategy_family=StrategyFamily.TREND,
        strategy_subfamily=StrategySubfamily.MOMENTUM_IMPULSE,
        description="Frozen Candidate 1: Intraday 15m directional impulse > 50 bps",
    ),
    "C2_OVERNIGHT_TREND": StrategyDefinition(
        strategy_id="C2_OVERNIGHT_TREND",
        strategy_family=StrategyFamily.TREND,
        strategy_subfamily=StrategySubfamily.OVERNIGHT_TREND,
        description="Frozen Candidate 2: 15:12 overnight trend >= 50 bps entry at 15:14",
    ),
    # Built-in strategies
    "OPENING_BREAKOUT": StrategyDefinition(
        strategy_id="OPENING_BREAKOUT",
        strategy_family=StrategyFamily.TREND,
        strategy_subfamily=StrategySubfamily.BREAKOUT,
        description="Opening range breakout / opening drive",
    ),
    "TREND_CONTINUATION": StrategyDefinition(
        strategy_id="TREND_CONTINUATION",
        strategy_family=StrategyFamily.TREND,
        strategy_subfamily=StrategySubfamily.CONTINUATION,
        description="Directional trend continuation and pullback",
    ),
    "MEAN_REVERSION": StrategyDefinition(
        strategy_id="MEAN_REVERSION",
        strategy_family=StrategyFamily.MEAN_REVERT,
        strategy_subfamily=StrategySubfamily.EXHAUSTION,
        description="Mean reversion on extended moves or failed breakouts",
    ),
    "RANGE_WATCHLIST": StrategyDefinition(
        strategy_id="RANGE_WATCHLIST",
        strategy_family=StrategyFamily.MEAN_REVERT,
        strategy_subfamily=StrategySubfamily.RANGE_WATCHLIST,
        description="Range-bound micro-pattern watchlist",
    ),
    "EVENT_VOLATILITY": StrategyDefinition(
        strategy_id="EVENT_VOLATILITY",
        strategy_family=StrategyFamily.DEFINED_RISK,
        strategy_subfamily=StrategySubfamily.EVENT_EXPANSION,
        description="Defined-risk volatility strategy for certified events",
    ),
    "NO_TRADE": StrategyDefinition(
        strategy_id="NO_TRADE",
        strategy_family=StrategyFamily.NO_TRADE,
        description="Explicit no-trade placeholder",
    ),
}


def get_strategy_definition(strategy_id: str) -> StrategyDefinition | None:
    norm_id = str(strategy_id or "").strip().upper()
    return STRATEGY_REGISTRY.get(norm_id)


def resolve_strategy_family(strategy_id: str) -> StrategyFamily:
    """Look up canonical strategy family from registry. Fails closed to NO_TRADE."""
    defn = get_strategy_definition(strategy_id)
    if defn is not None:
        return defn.strategy_family
    return StrategyFamily.NO_TRADE


def admit_candidate_to_pool(
    candidate_pool: list[dict[str, Any]],
    candidate: Any,
    *,
    compatibility_result: FamilyCompatibilityResult,
    trace_id: str | None = None,
) -> bool:
    """Canonical production candidate pool admission API.

    Enforces:
    1. Candidate must be compatible (compatibility_result.compatible == True).
    2. Zero order authority invariants (is_order_action=False, broker_write_authority=False).
    3. Deduplication: Rejects candidate if candidate_id or trade_id already exists in candidate_pool.
    4. Exact immutable identity preservation (candidate_id, strategy_id, strategy_family, trace_id).
    5. Returns True if admitted and appended to pool, False otherwise (fail-closed).
    """
    if not compatibility_result.compatible:
        return False

    candidate_id = getattr(candidate, "candidate_id", None)
    if not candidate_id and isinstance(candidate, dict):
        candidate_id = candidate.get("candidate_id") or candidate.get("trade_id")

    if not candidate_id:
        return False

    cand_id_str = str(candidate_id).strip()

    # Deduplication check: cannot admit duplicate candidate_id or trade_id
    for existing in candidate_pool:
        if not isinstance(existing, dict):
            continue
        existing_id = str(existing.get("candidate_id") or existing.get("trade_id") or "").strip()
        if existing_id and existing_id == cand_id_str:
            return False

    resolved_family = compatibility_result.candidate_family
    cand_family_str = (
        resolved_family.value
        if isinstance(resolved_family, StrategyFamily)
        else str(getattr(candidate, "strategy_family", "TREND"))
    )

    resolved_trace_id = trace_id or getattr(candidate, "trace_id", None)
    if not resolved_trace_id and isinstance(candidate, dict):
        resolved_trace_id = candidate.get("trace_id")

    admitted_dict: dict[str, Any] = {
        "candidate_id": cand_id_str,
        "trade_id": cand_id_str,
        "symbol": getattr(candidate, "symbol", None) or (candidate.get("symbol") if isinstance(candidate, dict) else ""),
        "strategy": getattr(candidate, "strategy_id", None) or (candidate.get("strategy") if isinstance(candidate, dict) else ""),
        "strategy_family": cand_family_str,
        "strategy_subfamily": getattr(candidate, "strategy_subfamily", None) or (candidate.get("strategy_subfamily") if isinstance(candidate, dict) else None),
        "candidate_origin": "c1_c2_pre_gate",
        "candidate_status": "advisory_only",
        "permission": "ADVISORY_ONLY",
        "final_action": "ADVISORY_ONLY",
        "execution_status": "advisory_only",
        "execution_entry_status": "advisory_only",
        "features": dict(getattr(candidate, "features", {}) or (candidate.get("features", {}) if isinstance(candidate, dict) else {})),
        "metadata": dict(getattr(candidate, "metadata", {}) or (candidate.get("metadata", {}) if isinstance(candidate, dict) else {})),
        "is_order_action": False,
        "broker_write_authority": False,
        "trace_id": str(resolved_trace_id or ""),
        "signal_timestamp": getattr(candidate, "signal_timestamp", None) or (candidate.get("signal_timestamp") if isinstance(candidate, dict) else None),
        "entry_boundary": getattr(candidate, "entry_boundary", None) or (candidate.get("entry_boundary") if isinstance(candidate, dict) else None),
        "exit_boundary": getattr(candidate, "exit_boundary", None) or (candidate.get("exit_boundary") if isinstance(candidate, dict) else None),
        "stop_rule": getattr(candidate, "stop_rule", None) or (candidate.get("stop_rule") if isinstance(candidate, dict) else None),
    }

    candidate_pool.append(admitted_dict)
    return True

