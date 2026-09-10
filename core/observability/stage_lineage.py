"""Stage Lineage and Stage Contracts for TradeBot Live Trace Pulse.

All components defined here are strictly read-only with respect to execution.
Order authority = false, broker write authority = false.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


class StageStatus(str, enum.Enum):
    PASS = "PASS"
    PASS_PARTIAL = "PASS_PARTIAL"
    DEGRADED_NONFATAL = "DEGRADED_NONFATAL"
    BLOCKED = "BLOCKED"
    FAIL_CLOSED = "FAIL_CLOSED"
    NOT_INVOKED = "NOT_INVOKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class PipelineCheckpoint(str, enum.Enum):
    MARKET_SESSION_STATE = "MARKET_SESSION_STATE"
    BROKER_KITE_CLIENT = "BROKER/KITE_CLIENT"
    WEBSOCKET_CONNECTION = "WEBSOCKET_CONNECTION"
    SUBSCRIPTION_REQUEST = "SUBSCRIPTION_REQUEST"
    SUBSCRIPTION_ACK = "SUBSCRIPTION_ACK"
    RAW_TICK_RECEIVE = "RAW_TICK_RECEIVE"
    TICK_NORMALIZATION = "TICK_NORMALIZATION"
    TICK_STORE = "TICK_STORE"
    DEPTH_STORE = "DEPTH_STORE"
    RUNTIME_FEED_TRUTH = "RUNTIME_FEED_TRUTH"
    FRESHNESS_GATE = "FRESHNESS_GATE"
    MARKET_MEMORY_BAR_AGGREGATION = "MARKET_MEMORY / BAR AGGREGATION"
    REGIME_MARKET_STATE = "REGIME / MARKET_STATE"
    STRATEGY_INPUT_ROUTER = "STRATEGY_INPUT_ROUTER"
    STRATEGY_EVALUATION = "STRATEGY_EVALUATION"
    CANDIDATE_EMISSION = "CANDIDATE_EMISSION"
    CANDIDATE_POOL = "CANDIDATE_POOL"
    CANDIDATE_FILTERS = "CANDIDATE_FILTERS"
    RISK_GOVERNANCE_GATE = "RISK/GOVERNANCE_GATE"
    RANKING = "RANKING"
    ADVISORY_DECISION_OUTPUT = "ADVISORY / DECISION OUTPUT"
    PERSISTENCE_EVIDENCE = "PERSISTENCE / EVIDENCE"
    CAS_PRIMITIVE_PATH = "CAS PRIMITIVE PATH"


CANONICAL_CHECKPOINT_ORDER: tuple[str, ...] = tuple(cp.value for cp in PipelineCheckpoint)


@dataclass(frozen=True)
class StageContractDefinition:
    checkpoint: str
    designed_purpose: str
    expected_input_desc: str
    expected_output_desc: str
    downstream_components: tuple[str, ...]


STAGE_CONTRACTS: dict[str, StageContractDefinition] = {
    PipelineCheckpoint.MARKET_SESSION_STATE.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.MARKET_SESSION_STATE.value,
        designed_purpose="Determine market calendar, holiday, trading hours, and active session boundary.",
        expected_input_desc="Current timestamp and exchange session schedule.",
        expected_output_desc="Market open/close status, session phase (PRE_OPEN, REGULAR, POST_CLOSE).",
        downstream_components=(PipelineCheckpoint.BROKER_KITE_CLIENT.value, PipelineCheckpoint.WEBSOCKET_CONNECTION.value),
    ),
    PipelineCheckpoint.BROKER_KITE_CLIENT.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.BROKER_KITE_CLIENT.value,
        designed_purpose="Maintain authenticated read-only session and API connectivity with broker.",
        expected_input_desc="Governed credentials / token file.",
        expected_output_desc="Validated read-only Kite session (profile, margins probe, instruments).",
        downstream_components=(PipelineCheckpoint.WEBSOCKET_CONNECTION.value, PipelineCheckpoint.SUBSCRIPTION_REQUEST.value),
    ),
    PipelineCheckpoint.WEBSOCKET_CONNECTION.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.WEBSOCKET_CONNECTION.value,
        designed_purpose="Establish and supervise reliable live market data WebSocket connection.",
        expected_input_desc="Active Kite session credentials and WS URL.",
        expected_output_desc="Connected WS transport state (connected=True).",
        downstream_components=(PipelineCheckpoint.SUBSCRIPTION_REQUEST.value, PipelineCheckpoint.RAW_TICK_RECEIVE.value),
    ),
    PipelineCheckpoint.SUBSCRIPTION_REQUEST.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.SUBSCRIPTION_REQUEST.value,
        designed_purpose="Request market data feeds for governed universe tokens.",
        expected_input_desc="Token list (underlying + option chain universe).",
        expected_output_desc="Binary subscribe request dispatched over WebSocket.",
        downstream_components=(PipelineCheckpoint.SUBSCRIPTION_ACK.value,),
    ),
    PipelineCheckpoint.SUBSCRIPTION_ACK.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.SUBSCRIPTION_ACK.value,
        designed_purpose="Verify broker acknowledgment and mode confirmation for requested tokens.",
        expected_input_desc="Broker acknowledgment message / subscription state.",
        expected_output_desc="Confirmed subscribed token count matching requested universe.",
        downstream_components=(PipelineCheckpoint.RAW_TICK_RECEIVE.value,),
    ),
    PipelineCheckpoint.RAW_TICK_RECEIVE.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.RAW_TICK_RECEIVE.value,
        designed_purpose="Receive binary tick packets from Kite WebSocket.",
        expected_input_desc="Incoming WebSocket binary stream.",
        expected_output_desc="Raw parsed tick payload list with timestamp.",
        downstream_components=(PipelineCheckpoint.TICK_NORMALIZATION.value,),
    ),
    PipelineCheckpoint.TICK_NORMALIZATION.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.TICK_NORMALIZATION.value,
        designed_purpose="Normalize raw ticks into standardized price, volume, OI, and depth structures.",
        expected_input_desc="Raw tick dictionaries/objects.",
        expected_output_desc="Normalized Tick objects with validated timestamp and token.",
        downstream_components=(PipelineCheckpoint.TICK_STORE.value, PipelineCheckpoint.DEPTH_STORE.value),
    ),
    PipelineCheckpoint.TICK_STORE.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.TICK_STORE.value,
        designed_purpose="Store recent normalized ticks in memory ring buffer.",
        expected_input_desc="Normalized tick stream.",
        expected_output_desc="Latest LTP, tick count, and age per instrument token.",
        downstream_components=(PipelineCheckpoint.RUNTIME_FEED_TRUTH.value, PipelineCheckpoint.MARKET_MEMORY_BAR_AGGREGATION.value),
    ),
    PipelineCheckpoint.DEPTH_STORE.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.DEPTH_STORE.value,
        designed_purpose="Maintain top-of-book and multi-level depth order book cache.",
        expected_input_desc="Normalized depth packets.",
        expected_output_desc="Current bid/ask, spread, and depth liquidity metrics.",
        downstream_components=(PipelineCheckpoint.RUNTIME_FEED_TRUTH.value, PipelineCheckpoint.CANDIDATE_FILTERS.value),
    ),
    PipelineCheckpoint.RUNTIME_FEED_TRUTH.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.RUNTIME_FEED_TRUTH.value,
        designed_purpose="Synthesize authoritative global and symbol feed health state.",
        expected_input_desc="Tick store, depth store, and transport connection states.",
        expected_output_desc="Canonical FeedHealthTruthDecision (feed_ok, reasons, symbol breakdown).",
        downstream_components=(PipelineCheckpoint.FRESHNESS_GATE.value,),
    ),
    PipelineCheckpoint.FRESHNESS_GATE.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.FRESHNESS_GATE.value,
        designed_purpose="Determine whether token observations meet freshness requirements.",
        expected_input_desc="Requested token universe + timestamps + freshness clock.",
        expected_output_desc="Freshness classification (HEALTHY, PARTIAL, DEGRADED, BLOCKED) with token evidence.",
        downstream_components=(PipelineCheckpoint.STRATEGY_INPUT_ROUTER.value,),
    ),
    PipelineCheckpoint.MARKET_MEMORY_BAR_AGGREGATION.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.MARKET_MEMORY_BAR_AGGREGATION.value,
        designed_purpose="Aggregate raw ticks into time/volume bars and indicator series.",
        expected_input_desc="Time-ordered tick stream.",
        expected_output_desc="Completed bars (1m, 5m, etc.) and indicator buffer (EMA, VWAP, ATR, RSI).",
        downstream_components=(PipelineCheckpoint.REGIME_MARKET_STATE.value, PipelineCheckpoint.STRATEGY_INPUT_ROUTER.value),
    ),
    PipelineCheckpoint.REGIME_MARKET_STATE.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.REGIME_MARKET_STATE.value,
        designed_purpose="Classify market state, volatility regime, and trend structure.",
        expected_input_desc="Aggregated bars and multi-timeframe indicators.",
        expected_output_desc="Regime label, trend direction, entropy/confidence score.",
        downstream_components=(PipelineCheckpoint.STRATEGY_INPUT_ROUTER.value, PipelineCheckpoint.CANDIDATE_FILTERS.value),
    ),
    PipelineCheckpoint.STRATEGY_INPUT_ROUTER.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.STRATEGY_INPUT_ROUTER.value,
        designed_purpose="Route verified market state and option chain inputs to registered strategies.",
        expected_input_desc="Fresh market snapshot, indicators, option universe, and regime state.",
        expected_output_desc="Targeted strategy input bundles dispatched to eligible strategies.",
        downstream_components=(PipelineCheckpoint.STRATEGY_EVALUATION.value,),
    ),
    PipelineCheckpoint.STRATEGY_EVALUATION.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.STRATEGY_EVALUATION.value,
        designed_purpose="Evaluate strategy alpha models against current market input.",
        expected_input_desc="Strategy-specific input bundle (indicators, regime, strikes).",
        expected_output_desc="Raw strategy setup/signal or explicit empty reason.",
        downstream_components=(PipelineCheckpoint.CANDIDATE_EMISSION.value,),
    ),
    PipelineCheckpoint.CANDIDATE_EMISSION.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.CANDIDATE_EMISSION.value,
        designed_purpose="Construct immutable candidate structures from qualifying strategy setups.",
        expected_input_desc="Raw strategy signals.",
        expected_output_desc="Emitted Candidate objects with immutable candidate_id.",
        downstream_components=(PipelineCheckpoint.CANDIDATE_POOL.value,),
    ),
    PipelineCheckpoint.CANDIDATE_POOL.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.CANDIDATE_POOL.value,
        designed_purpose="Aggregate and manage candidate pool for the cycle.",
        expected_input_desc="Emitted candidates from all evaluated strategies.",
        expected_output_desc="Aggregated candidate pool collection.",
        downstream_components=(PipelineCheckpoint.CANDIDATE_FILTERS.value,),
    ),
    PipelineCheckpoint.CANDIDATE_FILTERS.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.CANDIDATE_FILTERS.value,
        designed_purpose="Apply liquidity, spread, strike validity, and regime alignment filters.",
        expected_input_desc="Raw candidate pool + depth/quote quality metrics.",
        expected_output_desc="Qualified candidates surviving filters or attribution for filtered out items.",
        downstream_components=(PipelineCheckpoint.RISK_GOVERNANCE_GATE.value,),
    ),
    PipelineCheckpoint.RISK_GOVERNANCE_GATE.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.RISK_GOVERNANCE_GATE.value,
        designed_purpose="Apply portfolio risk limits, circuit breakers, and governance checks.",
        expected_input_desc="Filtered candidate set + portfolio state and risk limits.",
        expected_output_desc="Risk-approved candidates or explicit blocker reasons.",
        downstream_components=(PipelineCheckpoint.RANKING.value,),
    ),
    PipelineCheckpoint.RANKING.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.RANKING.value,
        designed_purpose="Rank and score approved candidates to determine top opportunities.",
        expected_input_desc="Risk-approved candidates + ranking scoring profiles.",
        expected_output_desc="Ordered candidate list with rank scores.",
        downstream_components=(PipelineCheckpoint.ADVISORY_DECISION_OUTPUT.value,),
    ),
    PipelineCheckpoint.ADVISORY_DECISION_OUTPUT.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.ADVISORY_DECISION_OUTPUT.value,
        designed_purpose="Produce read-only advisory suggestions and visibility bucket classification.",
        expected_input_desc="Ranked candidate list.",
        expected_output_desc="Advisory output (QUEUE_ONLY, ADVISORY_ONLY, EXECUTABLE_STATUS).",
        downstream_components=(PipelineCheckpoint.PERSISTENCE_EVIDENCE.value, PipelineCheckpoint.CAS_PRIMITIVE_PATH.value),
    ),
    PipelineCheckpoint.PERSISTENCE_EVIDENCE.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.PERSISTENCE_EVIDENCE.value,
        designed_purpose="Record immutable candidate journal, funnel, and decision artifacts.",
        expected_input_desc="Cycle results, candidate ledger, and funnel counts.",
        expected_output_desc="Persisted JSON/JSONL records in runtime directory.",
        downstream_components=(),
    ),
    PipelineCheckpoint.CAS_PRIMITIVE_PATH.value: StageContractDefinition(
        checkpoint=PipelineCheckpoint.CAS_PRIMITIVE_PATH.value,
        designed_purpose="Content-addressed storage and evidence hashing for auditability.",
        expected_input_desc="Output artifacts and evidence manifests.",
        expected_output_desc="Cryptographic hashes and sealed session ledger.",
        downstream_components=(),
    ),
}


@dataclass(frozen=True)
class StageRecord:
    """Immutable stage record emitted at each pipeline checkpoint.

    Original market data and runtime state are untouched.
    """

    trace_id: str
    stage_id: str
    component: str
    input_ref: str
    input_summary: Mapping[str, Any]
    expected_contract: str
    observed_contract: str
    action: str
    output_ref: str
    output_summary: Mapping[str, Any]
    status: str
    reason_code: str
    latency_us: int
    event_timestamp: str
    receive_timestamp: str
    emitted_timestamp: str
    is_order_action: bool = False  # is_order_action=false
    broker_write_authority: bool = False

    def validate(self) -> None:
        if not str(self.trace_id).strip():
            raise ValueError("stage_record_missing_trace_id")
        if not str(self.stage_id).strip():
            raise ValueError("stage_record_missing_stage_id")
        if not str(self.component).strip():
            raise ValueError("stage_record_missing_component")
        if self.status not in {s.value for s in StageStatus}:
            raise ValueError(f"stage_record_invalid_status: {self.status}")
        if self.is_order_action:  # is_order_action=false
            raise ValueError("stage_record_order_action_forbidden")
        if self.broker_write_authority:
            raise ValueError("stage_record_broker_write_forbidden")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_order_action"] = False
        data["broker_write_authority"] = False
        return data


def create_stage_record(
    *,
    trace_id: str,
    stage_id: str,
    component: str,
    input_ref: str = "",
    input_summary: Mapping[str, Any] | None = None,
    expected_contract: str = "",
    observed_contract: str = "",
    action: str = "",
    output_ref: str = "",
    output_summary: Mapping[str, Any] | None = None,
    status: str | StageStatus = StageStatus.PASS,
    reason_code: str = "OK",
    latency_us: int = 0,
    event_timestamp: str | None = None,
    receive_timestamp: str | None = None,
    emitted_timestamp: str | None = None,
) -> StageRecord:
    now_iso = datetime.now(timezone.utc).isoformat()
    status_str = status.value if isinstance(status, StageStatus) else str(status)
    record = StageRecord(
        trace_id=str(trace_id),
        stage_id=str(stage_id),
        component=str(component),
        input_ref=str(input_ref),
        input_summary=dict(input_summary or {}),
        expected_contract=str(expected_contract),
        observed_contract=str(observed_contract),
        action=str(action),
        output_ref=str(output_ref),
        output_summary=dict(output_summary or {}),
        status=status_str,
        reason_code=str(reason_code),
        latency_us=max(0, int(latency_us)),
        event_timestamp=str(event_timestamp or now_iso),
        receive_timestamp=str(receive_timestamp or now_iso),
        emitted_timestamp=str(emitted_timestamp or now_iso),
        is_order_action=False,
        broker_write_authority=False,
    )
    record.validate()
    return record
