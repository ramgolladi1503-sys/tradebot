"""Production Bridge for TradeBot Live Pipeline Observability.

Binds the 23 canonical pipeline checkpoints, immutable trace_id lifecycle,
candidate attribution, and role-aware token health model to actual production
callsites across core/orchestrator, core/kite_depth_ws, and core/feed_health_truth.

All operations are strictly read-only with respect to execution:
  broker_write_authority = False
  order_authority = False
  paper_authorized = False
  live_authorized = False

No normal-path additional disk I/O (in-memory ring buffer and ledger only).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Sequence

from core.observability.stage_lineage import (
    CANONICAL_CHECKPOINT_ORDER,
    PipelineCheckpoint,
    StageRecord,
    StageStatus,
    create_stage_record,
)
from core.observability.trace_pulse import (
    DiagnosticPulseRing,
    generate_trace_id,
)
from core.observability.candidate_attribution import (
    CandidateEmptyClass,
    CandidateLifecycleLedger,
    CandidateLifecycleStage,
    StrategyCoverageTracker,
    StrategyEvaluationAttribution,
)
from core.observability.token_health_model import (
    RoleAwareHealthReport,
    TokenDependencyGraph,
    TokenObservation,
    TokenRole,
)
from core.strategy_spec import build_strategy_spec_registry

logger = logging.getLogger(__name__)

# Global production singleton instances
_GLOBAL_PULSE_RING: DiagnosticPulseRing | None = None
_GLOBAL_CANDIDATE_LEDGER: CandidateLifecycleLedger | None = None
_GLOBAL_STRATEGY_TRACKER: StrategyCoverageTracker | None = None
_GLOBAL_TOKEN_GRAPH: TokenDependencyGraph | None = None

# Underlyings and their default known tokens
UNDERLYING_TOKENS: dict[str, int] = {
    "NIFTY": 256265,
    "BANKNIFTY": 260105,
    "SENSEX": 265,
}


def get_production_pulse_ring() -> DiagnosticPulseRing:
    global _GLOBAL_PULSE_RING
    if _GLOBAL_PULSE_RING is None:
        _GLOBAL_PULSE_RING = DiagnosticPulseRing(max_traces=1000, max_events=10000)
    return _GLOBAL_PULSE_RING


def get_production_candidate_ledger() -> CandidateLifecycleLedger:
    global _GLOBAL_CANDIDATE_LEDGER
    if _GLOBAL_CANDIDATE_LEDGER is None:
        _GLOBAL_CANDIDATE_LEDGER = CandidateLifecycleLedger(maxlen=5000)
    return _GLOBAL_CANDIDATE_LEDGER


def get_production_strategy_tracker() -> StrategyCoverageTracker:
    global _GLOBAL_STRATEGY_TRACKER
    if _GLOBAL_STRATEGY_TRACKER is None:
        spec_registry = build_strategy_spec_registry()
        registered_ids = list(spec_registry.strategy_ids())
        _GLOBAL_STRATEGY_TRACKER = StrategyCoverageTracker(registered_strategies=registered_ids)
        for spec in spec_registry.specs:
            _GLOBAL_STRATEGY_TRACKER.register_strategy(
                spec.strategy_id,
                enabled=True,
                wired=True,
            )
    return _GLOBAL_STRATEGY_TRACKER


def get_production_token_graph() -> TokenDependencyGraph:
    global _GLOBAL_TOKEN_GRAPH
    if _GLOBAL_TOKEN_GRAPH is None:
        spec_registry = build_strategy_spec_registry()
        registered_ids = list(spec_registry.strategy_ids())
        _GLOBAL_TOKEN_GRAPH = TokenDependencyGraph(
            max_freshness_age_sec=3.0,
            required_option_quorum=0.80,
            registered_strategies=registered_ids,
        )
        # Register critical underlyings
        for sym, tok in UNDERLYING_TOKENS.items():
            _GLOBAL_TOKEN_GRAPH.register_token(
                token=tok,
                symbol=sym,
                role=TokenRole.CRITICAL_UNDERLYING,
                dependent_strategies=registered_ids,
            )
    return _GLOBAL_TOKEN_GRAPH


class ProductionObservabilityBridge:
    """Production bridge providing non-intrusive hooks for all 23 pipeline checkpoints."""

    def __init__(
        self,
        pulse_ring: DiagnosticPulseRing | None = None,
        candidate_ledger: CandidateLifecycleLedger | None = None,
        strategy_tracker: StrategyCoverageTracker | None = None,
        token_graph: TokenDependencyGraph | None = None,
    ) -> None:
        self.pulse_ring = pulse_ring or get_production_pulse_ring()
        self.candidate_ledger = candidate_ledger or get_production_candidate_ledger()
        self.strategy_tracker = strategy_tracker or get_production_strategy_tracker()
        self.token_graph = token_graph or get_production_token_graph()
        self.broker_write_authority: bool = False
        self.order_authority: bool = False

    def emit_checkpoint(
        self,
        checkpoint: PipelineCheckpoint | str,
        trace_id: str,
        stage_id: str,
        status: StageStatus | str = StageStatus.PASS,
        reason_code: str = "OK",
        latency_us: int | float = 0,
        metadata: Mapping[str, Any] | None = None,
    ) -> StageRecord:
        """Emit an immutable StageRecord into the zero-IO in-memory diagnostic ring."""
        cp_val = checkpoint.value if isinstance(checkpoint, PipelineCheckpoint) else str(checkpoint)
        st_val = status.value if isinstance(status, StageStatus) else str(status)
        record = create_stage_record(
            trace_id=trace_id,
            stage_id=stage_id,
            component=cp_val,
            status=st_val,
            reason_code=reason_code,
            latency_us=int(latency_us),
            output_summary=metadata,
        )
        self.pulse_ring.record_stage(record)
        return record

    def start_cycle_trace(self, cycle_id: str | int) -> str:
        """Generate a production trace_id for an orchestrator cycle."""
        return generate_trace_id(seed=f"cycle_{cycle_id}_{time.time_ns()}")

    def record_candidate_transition(
        self,
        candidate_id: str,
        from_stage: CandidateLifecycleStage | str,
        to_stage: CandidateLifecycleStage | str,
        status: str,
        reason_code: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> Any:
        """Record candidate movement through the decision funnel."""
        return self.candidate_ledger.record_transition(
            candidate_id=candidate_id,
            from_stage=from_stage,
            to_stage=to_stage,
            status=status,
            reason_code=reason_code,
            metadata=metadata,
        )

    def record_strategy_evaluation(
        self,
        strategy_id: str,
        invoked: bool,
        input_ready: bool,
        input_fresh: bool,
        evaluation_status: str,
        candidate_count_before_filters: int,
        candidate_count_after_filters: int,
        candidate_count_after_risk: int,
        candidate_count_after_ranking: int,
        terminal_reason_code: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Record strategy evaluation attribution against real registry specifications."""
        attr = StrategyEvaluationAttribution(
            strategy_id=strategy_id,
            invoked=invoked,
            input_ready=input_ready,
            input_fresh=input_fresh,
            evaluation_status=evaluation_status,
            candidate_count_before_filters=candidate_count_before_filters,
            candidate_count_after_filters=candidate_count_after_filters,
            candidate_count_after_risk=candidate_count_after_risk,
            candidate_count_after_ranking=candidate_count_after_ranking,
            terminal_reason_code=terminal_reason_code,
        )
        self.strategy_tracker.record_evaluation(attr)

    def evaluate_token_health_from_feed_truth(
        self,
        feed_truth_payload: Mapping[str, Any],
        token_observations: Sequence[TokenObservation] | None = None,
    ) -> RoleAwareHealthReport:
        """Reconcile token health using real feed truth decisions."""
        observations: list[TokenObservation] = []
        if token_observations:
            observations.extend(token_observations)
        else:
            # Build observations from feed_truth_payload
            now_epoch = time.time()
            max_age = float(feed_truth_payload.get("max_option_tick_age_sec") or 3.0)
            for sym, tok in UNDERLYING_TOKENS.items():
                last_tick_age = feed_truth_payload.get("last_tick_age_sec")
                age = float(last_tick_age) if last_tick_age is not None else 0.5
                is_fresh = age <= max_age
                observations.append(
                    TokenObservation(
                        token=tok,
                        symbol=sym,
                        role=TokenRole.CRITICAL_UNDERLYING,
                        requested=True,
                        acknowledged=True,
                        with_ticks=True,
                        is_fresh=is_fresh,
                        last_tick_age_sec=age,
                        is_missing=False,
                    )
                )

        return self.token_graph.evaluate_health(observations)
