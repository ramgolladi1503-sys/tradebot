"""Elite movement strategy candidate contract.

This module defines the shared schema for the future opportunity engine.
It is contract-only: no broker calls, no order calls, no execution gate changes,
no depth subscription changes, and no strategy tuning.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Direction = Literal["BUY_CALL", "BUY_PUT", "NO_TRADE"]
CandidateStatus = Literal[
    "RAW_CANDIDATE",
    "VALIDATED_CANDIDATE",
    "BLOCKED_CANDIDATE",
    "RANKED_OPPORTUNITY",
    "NO_TRADE",
]
MovementType = Literal[
    "OPENING_DRIVE",
    "OPENING_RANGE_RETEST",
    "COMPRESSION_BREAKOUT",
    "TREND_PULLBACK",
    "VWAP_RECLAIM_REJECTION",
    "FAILED_BREAKOUT_TRAP",
    "EXHAUSTION_REVERSAL",
    "MEAN_REVERSION_EXTENSION",
    "EVENT_VOLATILITY_EXPANSION",
    "OPTION_PRESSURE_CONFIRMATION",
    "LATE_DAY_MOMENTUM",
    "NO_TRADE_CHOP",
    "LEGACY_SIGNAL",
]

VALID_DIRECTIONS: frozenset[str] = frozenset({"BUY_CALL", "BUY_PUT", "NO_TRADE"})
VALID_CANDIDATE_STATUSES: frozenset[str] = frozenset(
    {
        "RAW_CANDIDATE",
        "VALIDATED_CANDIDATE",
        "BLOCKED_CANDIDATE",
        "RANKED_OPPORTUNITY",
        "NO_TRADE",
    }
)
VALID_MOVEMENT_TYPES: frozenset[str] = frozenset(
    {
        "OPENING_DRIVE",
        "OPENING_RANGE_RETEST",
        "COMPRESSION_BREAKOUT",
        "TREND_PULLBACK",
        "VWAP_RECLAIM_REJECTION",
        "FAILED_BREAKOUT_TRAP",
        "EXHAUSTION_REVERSAL",
        "MEAN_REVERSION_EXTENSION",
        "EVENT_VOLATILITY_EXPANSION",
        "OPTION_PRESSURE_CONFIRMATION",
        "LATE_DAY_MOMENTUM",
        "NO_TRADE_CHOP",
        "LEGACY_SIGNAL",
    }
)

HARD_EXECUTION_BLOCKERS: frozenset[str] = frozenset(
    {
        "STALE_OPTION_LTP",
        "WIDE_SPREAD",
        "MISSING_DEPTH",
        "FALLBACK_QUOTE_ONLY",
        "UNRESOLVED_CONTRACT",
        "CONFLICTING_TRAP_SIGNAL",
        "NO_TRADE_CHOP",
        "BROKER_UNAVAILABLE",
        "MARKET_CLOSED",
        "QUOTE_SOURCE_UNTRUSTED",
        "OPTION_CONFIRMATION_MISSING",
    }
)

SCORE_FIELDS: tuple[str, ...] = (
    "raw_score",
    "confidence_score",
    "price_structure_score",
    "option_confirmation_score",
    "liquidity_score",
    "freshness_score",
    "volatility_score",
    "regime_alignment_score",
    "timing_score",
    "trap_risk_score",
    "confluence_score",
)

STRATEGY_OWNED_SCORE_FIELDS: tuple[str, ...] = (
    "raw_score",
    "confidence_score",
    "price_structure_score",
    "volatility_score",
    "regime_alignment_score",
    "timing_score",
    "trap_risk_score",
    "confluence_score",
)

PHASE2_OWNED_SCORE_FIELDS: tuple[str, ...] = (
    "option_confirmation_score",
    "liquidity_score",
    "freshness_score",
)

PHASE2_TRUTH_EVIDENCE_KEYS: frozenset[str] = frozenset(
    {
        "quote_source",
        "fallback_used",
        "option_ltp_age_sec",
        "ce_spread_pct",
        "pe_spread_pct",
        "ce_depth",
        "pe_depth",
        "resolved_instrument",
        "resolved_contract",
        "execution_eligible",
        "liquidity_truth",
        "freshness_truth",
        "option_confirmation_truth",
    }
)

PHASE2_NEUTRAL_SCORE = 0.5


class MovementContractError(ValueError):
    """Raised when a movement candidate violates the contract."""


def _clean_text(value: Any, *, field_name: str, uppercase: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        raise MovementContractError(f"missing_required_field:{field_name}")
    return text.upper() if uppercase else text


def _score(value: Any, *, field_name: str) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise MovementContractError(f"score_not_numeric:{field_name}") from exc
    if not math.isfinite(out):
        raise MovementContractError(f"score_not_finite:{field_name}")
    if out < 0.0 or out > 1.0:
        raise MovementContractError(f"score_out_of_range:{field_name}:{out}")
    return out


def _optional_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception as exc:
        raise MovementContractError(f"float_not_numeric:{field_name}") from exc
    if not math.isfinite(out):
        raise MovementContractError(f"float_not_finite:{field_name}")
    return out


def _text_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    return tuple(str(item).strip() for item in values if str(item).strip())


def _score_map(values: dict[str, Any] | None, *, field_name: str) -> dict[str, float]:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise MovementContractError(f"score_map_not_dict:{field_name}")
    return {str(key).strip().upper(): _score(value, field_name=f"{field_name}.{key}") for key, value in values.items() if str(key).strip()}


def _jsonable_map(values: dict[str, Any] | None, *, field_name: str) -> dict[str, Any]:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise MovementContractError(f"map_not_dict:{field_name}")
    try:
        json.dumps(values, sort_keys=True, default=str)
    except Exception as exc:
        raise MovementContractError(f"map_not_json_serializable:{field_name}") from exc
    return dict(values)


def has_hard_blocker(blockers: tuple[str, ...] | list[str] | None) -> bool:
    normalized = {str(item).strip().upper() for item in (blockers or [])}
    return bool(normalized.intersection(HARD_EXECUTION_BLOCKERS))


def phase2_boundary_violations(candidate: "StrategyCandidate", *, producer_stage: str) -> tuple[str, ...]:
    """Return ownership-boundary violations without mutating candidate state.

    Strategy producers own thesis and price-structure evidence. Phase-2 producers
    own tradability truth: option confirmation, liquidity, freshness, and resolved
    execution evidence. This helper is opt-in so PR #528 introduces a contract
    guard without changing current runtime behavior.
    """

    stage = _clean_text(producer_stage, field_name="producer_stage", uppercase=True)
    if stage in {"PHASE2", "PHASE_2", "CANDIDATE_FACTORY"}:
        return ()
    if stage not in {"STRATEGY", "STRATEGY_MODULE", "MOVEMENT_STRATEGY"}:
        raise MovementContractError(f"invalid_producer_stage:{stage}")

    violations: list[str] = []
    for field_name in PHASE2_OWNED_SCORE_FIELDS:
        value = getattr(candidate, field_name)
        if value != PHASE2_NEUTRAL_SCORE:
            violations.append(f"strategy_candidate_claims_phase2_score:{field_name}")

    evidence_keys = {str(key).strip().lower() for key in candidate.evidence.keys()}
    for key in sorted(PHASE2_TRUTH_EVIDENCE_KEYS):
        if key.lower() in evidence_keys:
            violations.append(f"strategy_candidate_claims_phase2_evidence:{key}")

    if candidate.status == "RANKED_OPPORTUNITY":
        violations.append("strategy_candidate_claims_ranked_opportunity")
    return tuple(violations)


def assert_phase2_boundary(candidate: "StrategyCandidate", *, producer_stage: str) -> "StrategyCandidate":
    violations = phase2_boundary_violations(candidate, producer_stage=producer_stage)
    if violations:
        raise MovementContractError(";".join(violations))
    return candidate


@dataclass(frozen=True)
class StrategyCandidate:
    """A movement strategy proposal emitted into the candidate pool.

    This is not a trade. It is not executable truth. Later layers must confirm
    option quality, freshness, liquidity, blockers, and execution eligibility.
    """

    schema_version: int
    strategy_id: str
    movement_type: str
    symbol: str
    direction: Direction
    status: CandidateStatus

    raw_score: float
    confidence_score: float
    price_structure_score: float
    option_confirmation_score: float
    liquidity_score: float
    freshness_score: float
    volatility_score: float
    regime_alignment_score: float
    timing_score: float = 0.5
    trap_risk_score: float = 0.0
    confluence_score: float = 0.0

    entry_trigger: str = "not_specified"
    invalid_if: str = "not_specified"
    rank_reason: str = "not_ranked"

    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    confluence_tags: tuple[str, ...] = ()
    suppression_tags: tuple[str, ...] = ()
    source_signals: tuple[str, ...] = ()

    regime_scores: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    generated_epoch: float = field(default_factory=time.time)

    CURRENT_SCHEMA_VERSION: int = 1

    def __post_init__(self) -> None:
        schema = int(self.schema_version)
        if schema != self.CURRENT_SCHEMA_VERSION:
            raise MovementContractError(f"unsupported_schema_version:{schema}")

        strategy_id = _clean_text(self.strategy_id, field_name="strategy_id")
        movement_type = _clean_text(self.movement_type, field_name="movement_type", uppercase=True)
        if movement_type not in VALID_MOVEMENT_TYPES:
            raise MovementContractError(f"invalid_movement_type:{movement_type}")
        symbol = _clean_text(self.symbol, field_name="symbol", uppercase=True)

        direction = _clean_text(self.direction, field_name="direction", uppercase=True)
        if direction not in VALID_DIRECTIONS:
            raise MovementContractError(f"invalid_direction:{direction}")
        status = _clean_text(self.status, field_name="status", uppercase=True)
        if status not in VALID_CANDIDATE_STATUSES:
            raise MovementContractError(f"invalid_status:{status}")

        blockers = _text_tuple(self.blockers)
        warnings = _text_tuple(self.warnings)
        confluence_tags = _text_tuple(self.confluence_tags)
        suppression_tags = _text_tuple(self.suppression_tags)
        source_signals = _text_tuple(self.source_signals)

        if status == "NO_TRADE" and direction != "NO_TRADE":
            raise MovementContractError("no_trade_status_requires_no_trade_direction")
        if direction == "NO_TRADE" and status != "NO_TRADE":
            raise MovementContractError("no_trade_direction_requires_no_trade_status")
        if status == "RANKED_OPPORTUNITY" and has_hard_blocker(blockers):
            raise MovementContractError("ranked_opportunity_has_hard_blocker")

        generated_epoch = _optional_float(self.generated_epoch, field_name="generated_epoch")
        if generated_epoch is None:
            generated_epoch = time.time()

        object.__setattr__(self, "schema_version", schema)
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "movement_type", movement_type)
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "raw_score", _score(self.raw_score, field_name="raw_score"))
        object.__setattr__(self, "confidence_score", _score(self.confidence_score, field_name="confidence_score"))
        object.__setattr__(self, "price_structure_score", _score(self.price_structure_score, field_name="price_structure_score"))
        object.__setattr__(self, "option_confirmation_score", _score(self.option_confirmation_score, field_name="option_confirmation_score"))
        object.__setattr__(self, "liquidity_score", _score(self.liquidity_score, field_name="liquidity_score"))
        object.__setattr__(self, "freshness_score", _score(self.freshness_score, field_name="freshness_score"))
        object.__setattr__(self, "volatility_score", _score(self.volatility_score, field_name="volatility_score"))
        object.__setattr__(self, "regime_alignment_score", _score(self.regime_alignment_score, field_name="regime_alignment_score"))
        object.__setattr__(self, "timing_score", _score(self.timing_score, field_name="timing_score"))
        object.__setattr__(self, "trap_risk_score", _score(self.trap_risk_score, field_name="trap_risk_score"))
        object.__setattr__(self, "confluence_score", _score(self.confluence_score, field_name="confluence_score"))
        object.__setattr__(self, "entry_trigger", _clean_text(self.entry_trigger, field_name="entry_trigger"))
        object.__setattr__(self, "invalid_if", _clean_text(self.invalid_if, field_name="invalid_if"))
        object.__setattr__(self, "rank_reason", _clean_text(self.rank_reason, field_name="rank_reason"))
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "confluence_tags", confluence_tags)
        object.__setattr__(self, "suppression_tags", suppression_tags)
        object.__setattr__(self, "source_signals", source_signals)
        object.__setattr__(self, "regime_scores", _score_map(self.regime_scores, field_name="regime_scores"))
        object.__setattr__(self, "evidence", _jsonable_map(self.evidence, field_name="evidence"))
        object.__setattr__(self, "lineage", _jsonable_map(self.lineage, field_name="lineage"))
        object.__setattr__(self, "generated_epoch", generated_epoch)

    @property
    def has_hard_blocker(self) -> bool:
        return has_hard_blocker(self.blockers)

    @property
    def executable_eligible(self) -> bool:
        return self.status in {"VALIDATED_CANDIDATE", "RANKED_OPPORTUNITY"} and not self.has_hard_blocker

    def phase2_boundary_violations(self, *, producer_stage: str) -> tuple[str, ...]:
        return phase2_boundary_violations(self, producer_stage=producer_stage)

    def assert_phase2_boundary(self, *, producer_stage: str) -> "StrategyCandidate":
        return assert_phase2_boundary(self, producer_stage=producer_stage)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blockers"] = list(self.blockers)
        data["warnings"] = list(self.warnings)
        data["confluence_tags"] = list(self.confluence_tags)
        data["suppression_tags"] = list(self.suppression_tags)
        data["source_signals"] = list(self.source_signals)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


@dataclass(frozen=True)
class StrategyContext:
    """Elite-ready shared input context for future movement strategies.

    Missing evidence should produce blockers/warnings in candidate output, not
    crashes in strategy code.
    """

    symbol: str
    ts_epoch: float | None = None
    spot_ltp: float | None = None
    open_price: float | None = None
    vwap: float | None = None
    vwap_slope: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    orb_high: float | None = None
    orb_low: float | None = None
    prev_day_high: float | None = None
    prev_day_low: float | None = None
    nearest_support: float | None = None
    nearest_resistance: float | None = None
    atr: float | None = None
    atr_short: float | None = None
    atr_long: float | None = None
    range_width_pct: float | None = None
    volume_z: float | None = None
    volatility_state: str | None = None
    regime_hint: str | None = None
    regime_scores: dict[str, float] = field(default_factory=dict)
    option_ce_ltp: float | None = None
    option_pe_ltp: float | None = None
    ce_premium_change: float | None = None
    pe_premium_change: float | None = None
    ce_spread_pct: float | None = None
    pe_spread_pct: float | None = None
    ce_depth: float | None = None
    pe_depth: float | None = None
    option_ltp_age_sec: float | None = None
    quote_source: str | None = None
    fallback_used: bool = False
    time_of_day: str | None = None
    minutes_since_open: int | None = None
    minutes_to_close: int | None = None
    expiry_context: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _clean_text(self.symbol, field_name="symbol", uppercase=True))
        object.__setattr__(self, "ts_epoch", _optional_float(self.ts_epoch, field_name="ts_epoch"))
        object.__setattr__(self, "regime_scores", _score_map(self.regime_scores, field_name="regime_scores"))
        object.__setattr__(self, "metadata", _jsonable_map(self.metadata, field_name="metadata"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


def candidate_from_dict(payload: dict[str, Any]) -> StrategyCandidate:
    if not isinstance(payload, dict):
        raise MovementContractError("candidate_payload_not_dict")
    return StrategyCandidate(**payload)


def context_from_dict(payload: dict[str, Any]) -> StrategyContext:
    if not isinstance(payload, dict):
        raise MovementContractError("context_payload_not_dict")
    return StrategyContext(**payload)


__all__ = [
    "CandidateStatus",
    "Direction",
    "HARD_EXECUTION_BLOCKERS",
    "MovementContractError",
    "MovementType",
    "PHASE2_NEUTRAL_SCORE",
    "PHASE2_OWNED_SCORE_FIELDS",
    "PHASE2_TRUTH_EVIDENCE_KEYS",
    "SCORE_FIELDS",
    "STRATEGY_OWNED_SCORE_FIELDS",
    "StrategyCandidate",
    "StrategyContext",
    "VALID_CANDIDATE_STATUSES",
    "VALID_DIRECTIONS",
    "VALID_MOVEMENT_TYPES",
    "assert_phase2_boundary",
    "candidate_from_dict",
    "context_from_dict",
    "has_hard_blocker",
    "phase2_boundary_violations",
]
