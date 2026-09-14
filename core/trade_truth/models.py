"""Canonical immutable models for Trade Truth Layer.

Schema Version: 1
Scope: Identity, Timing, Market, Analytical, Decision, Provenance, Execution, and Outcome Truth.
Safety Guarantee: Read-only, order_action=False, broker_api_called=False.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping, Sequence

TRUTH_SCHEMA_VERSION = 1
TRUTH_SOURCE = "tradebot.trade_truth.v1"

# Explicit failure / degraded states
TRUTH_INCOMPLETE = "TRUTH_INCOMPLETE"
TRUTH_CORRUPT = "TRUTH_CORRUPT"
TRUTH_SCHEMA_MISMATCH = "TRUTH_SCHEMA_MISMATCH"
TRUTH_SEQUENCE_GAP = "TRUTH_SEQUENCE_GAP"
TRUTH_STALE = "TRUTH_STALE"
REPLAY_DIVERGENCE = "REPLAY_DIVERGENCE"
FORENSIC_DIVERGENCE = "FORENSIC_DIVERGENCE"
EXECUTION_TRUTH_UNKNOWN = "EXECUTION_TRUTH_UNKNOWN"


def _safe_float(val: Any) -> float | None:
    if val in (None, "", "None"):
        return None
    try:
        f = float(val)
        return f if f == f else None
    except Exception:
        return None


def _safe_int(val: Any) -> int | None:
    if val in (None, "", "None"):
        return None
    try:
        return int(val)
    except Exception:
        return None


def _safe_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    return str(val).strip()


@dataclass(frozen=True)
class IdentityTruth:
    truth_record_id: str
    trace_id: str
    session_id: str
    candidate_id: str
    strategy_id: str
    instrument: str
    parent_trace_id: str | None = None
    underlying: str | None = None
    option_type: str | None = None  # CE / PE
    strike: float | None = None
    expiry: str | None = None
    lot_size: int | None = None


@dataclass(frozen=True)
class TimingTruth:
    exchange_timestamp_iso: str | None = None
    receive_timestamp_iso: str | None = None
    normalization_timestamp_iso: str | None = None
    decision_timestamp_iso: str | None = None
    execution_boundary_timestamp_iso: str | None = None
    exchange_timestamp_epoch: float | None = None
    receive_timestamp_epoch: float | None = None
    normalization_timestamp_epoch: float | None = None
    decision_timestamp_epoch: float | None = None  # None if unrecorded; NEVER manufactured
    execution_boundary_timestamp_epoch: float | None = None
    feed_age_ms: float | None = None
    ingestion_latency_ms: float | None = None
    decision_latency_ms: float | None = None


@dataclass(frozen=True)
class MarketTruth:
    underlying: str
    ltp: float | None
    bid: float | None = None
    ask: float | None = None
    bid_qty: int | None = None
    ask_qty: int | None = None
    depth: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    spread: float | None = None
    spread_pct: float | None = None
    volume: int | None = None
    oi: int | None = None
    iv: float | None = None
    feed_age_sec: float | None = None
    data_source: str = "UNKNOWN"
    feed_state: str = "UNKNOWN"
    tick_sequence: int | None = None
    sequence_gap_status: str = "UNKNOWN"  # Defaults conservatively to UNKNOWN
    market_state_integrity: str = "UNKNOWN"  # Defaults conservatively to UNKNOWN


@dataclass(frozen=True)
class AnalyticalTruth:
    regime: str = "UNKNOWN"
    regime_confidence: float | None = None
    regime_probabilities: dict[str, float] = field(default_factory=dict)
    features_used: dict[str, Any] = field(default_factory=dict)
    strategy_output: dict[str, Any] = field(default_factory=dict)
    model_outputs: dict[str, Any] = field(default_factory=dict)
    signal_confidence: float | None = None
    volatility_state: str = "UNKNOWN"
    liquidity_state: str = "UNKNOWN"
    intraday_memory_refs: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DecisionTruth:
    candidate_generated: bool
    candidate_score: float | None
    rank: int | None
    ranking_reasons: tuple[str, ...] = field(default_factory=tuple)
    option_selection_reason: str | None = None
    risk_result: str = "UNKNOWN"  # Defaults conservatively to UNKNOWN
    blockers: tuple[str, ...] = field(default_factory=tuple)
    governance_decision: str = "BLOCKED"  # ALLOWED, BLOCKED, NO_TRADE
    final_action: str = "NO_TRADE"  # ENTRY, EXIT, NO_TRADE, OBSERVE
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProvenanceTruth:
    git_sha: str
    dirty_tree: bool
    config_hash: str
    model_hash: str | None = None
    model_version: str | None = None
    feature_schema_version: int = 1
    strategy_version: str = "1.0.0"
    truth_schema_version: int = TRUTH_SCHEMA_VERSION
    runtime_version: str = "1.0.0"
    build_id: str | None = None


@dataclass(frozen=True)
class ExecutionTruth:
    intended_action: str  # BUY_CALL, BUY_PUT, NO_TRADE, etc.
    intended_entry: float | None
    executable_market_state: str  # EXECUTABLE, NOT_EXECUTABLE, UNKNOWN
    theoretical_executable_price: float | None
    execution_type: str = "SIMULATED"  # OBSERVED_MARKET_EXECUTABILITY, SIMULATED, ACTUAL_EXECUTION
    broker_submission_authorized: bool = False
    actual_broker_submission: bool = False
    actual_broker_acknowledgment: bool = False
    actual_fill: bool = False
    fill_quantity: int = 0
    fill_price: float | None = None
    partial_fill_state: str = "NONE"
    execution_latency_ms: float | None = None
    observed_slippage: float | None = None
    spread_cost: float | None = None
    estimated_fees: float | None = None
    rejection_reason: str | None = None
    is_counterfactual: bool = False


@dataclass(frozen=True)
class HorizonOutcome:
    horizon_minutes: int
    forward_price: float | None
    price_basis: str  # LTP, BID, ASK, MID
    mfe_abs: float | None = None
    mae_abs: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    target_hit: bool = False
    stop_hit: bool = False
    timeout: bool = False


@dataclass(frozen=True)
class OutcomeTruth:
    is_counterfactual: bool
    status: str  # OBSERVED, PENDING, UNKNOWN, MARKET_CLOSED
    price_basis: str = "LTP"
    horizons: dict[str, dict[str, Any]] = field(default_factory=dict)
    mfe_abs: float | None = None
    mae_abs: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    realized_outcome: str | None = None  # TARGET_HIT, STOP_HIT, TIMEOUT, NO_OBSERVATIONS
    attribution_primary: str = "UNKNOWN"
    attribution_secondary: tuple[str, ...] = field(default_factory=tuple)
    attribution_confidence: float | None = None
    attribution_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TradeTruthRecord:
    schema_version: int
    source: str
    identity: IdentityTruth
    timing: TimingTruth
    market: MarketTruth
    analytical: AnalyticalTruth
    decision: DecisionTruth
    provenance: ProvenanceTruth
    execution: ExecutionTruth
    outcome: OutcomeTruth
    live_decision_hash: str
    record_hash: str
    sequence_number: int = 1
    previous_record_hash: str = "GENESIS"
    record_type: str = "DECISION_TRUTH"  # DECISION_TRUTH, OUTCOME_AMENDMENT, CORRECTION
    parent_truth_record_id: str | None = None
    read_only: bool = True
    append_only: bool = True
    is_order_action: bool = False
    broker_api_called: bool = False
    orders_placed: int = 0
    orders_modified: int = 0
    orders_cancelled: int = 0
    integrity_status: str = "VALID"  # VALID, CORRUPT, AMENDED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
