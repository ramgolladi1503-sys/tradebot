from dataclasses import dataclass, field
from typing import Optional, List
from .evidence_types import (
    CandidateSourceStatus, ExecutionEligibility, OutcomeStatus,
    ExitReason, EvidenceQuality, CostModelStatus
)


@dataclass(frozen=True)
class OptionTracePoint:
    timestamp: float
    ltp: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    oi: Optional[int] = None
    spread: Optional[float] = None


@dataclass(frozen=True)
class MarketSnapshotEvidence:
    timestamp: float
    underlying_ltp: float
    index_name: str


@dataclass(frozen=True)
class ReplayCandidate:
    candidate_id: Optional[str]
    strategy_id: Optional[str]
    timestamp: float
    instrument_id: Optional[str]
    underlying: Optional[str]
    entry_price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    strategy_version: Optional[str] = None
    option_symbol: Optional[str] = None
    strike: Optional[float] = None
    expiry: Optional[str] = None
    option_type: Optional[str] = None
    time_stop: Optional[float] = None
    execution_ok: bool = False
    blockers: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    ranking_bucket: Optional[str] = None
    source_path: Optional[str] = None
    source_offset: Optional[int] = None
    source_status: CandidateSourceStatus = CandidateSourceStatus.LOADED
    evidence_quality: EvidenceQuality = EvidenceQuality.COMPLETE


@dataclass(frozen=True)
class CandidateDecisionEvidence:
    candidate: ReplayCandidate
    eligibility: ExecutionEligibility


@dataclass(frozen=True)
class OutcomeWindow:
    start_time: float
    end_time: float
    duration_seconds: float


@dataclass(frozen=True)
class MfeMaeEvidence:
    mfe_points: float
    mae_points: float
    mfe_r: float
    mae_r: float
    realized_r: float
    max_drawdown: float
    time_to_mfe: float
    time_to_mae: float
    hold_duration: float


@dataclass(frozen=True)
class CostComponent:
    name: str
    value: float
    source_origin: str
    is_estimated: bool
    bid_ask_available: bool


@dataclass(frozen=True)
class CostBreakdown:
    components: List[CostComponent]
    total_cost: float
    lot_size: int
    status: CostModelStatus


@dataclass(frozen=True)
class ExecutionSimulation:
    entry_fill: float
    exit_fill: float
    spread_impact: float
    slippage_impact: float
    delayed_entry: bool
    delayed_exit: bool
    is_hypothetical_rejected: bool


@dataclass(frozen=True)
class ReplayOutcome:
    status: OutcomeStatus
    exit_reason: ExitReason
    exit_time: Optional[float]
    exit_price: Optional[float]
    gross_pnl: float
    window: OutcomeWindow
    mfe_mae: Optional[MfeMaeEvidence]


@dataclass(frozen=True)
class RegimeContextEvidence:
    trend: Optional[str] = None
    range_status: Optional[str] = None
    entropy: Optional[float] = None
    volatility: Optional[float] = None
    iv_bucket: Optional[str] = None
    session_bucket: Optional[str] = None
    is_expiry_day: Optional[bool] = None
    liquidity_bucket: Optional[str] = None
    spread_bucket: Optional[str] = None
    mip_event_context: Optional[str] = None


@dataclass(frozen=True)
class OutcomeEvidenceRecord:
    run_id: str
    candidate_id: str
    strategy_id: str
    input_source: str
    evidence_quality: EvidenceQuality
    outcome_status: OutcomeStatus
    exit_reason: ExitReason
    mfe_mae: Optional[MfeMaeEvidence]
    cost_breakdown: CostBreakdown
    gross_pnl: float
    net_pnl: float
    regime_context: RegimeContextEvidence
    simulation: ExecutionSimulation
    warnings: List[str]
    created_timestamp: float


@dataclass(frozen=True)
class OutcomeEvidenceRunSummary:
    run_id: str
    run_status: str
    total_candidates: int
    executable_count: int
    rejected_count: int
    insufficient_evidence_count: int
    ambiguous_count: int
    weak_ltp_count: int
    start_time: float
    end_time: float
