"""Candidate Attribution, Strategy Coverage Matrix, and Lifecycle Ledger.

Explains why the candidate pool is empty (no setup vs not invoked vs stale vs filtered vs blocked)
and tracks each candidate's transition across the decision funnel.
Read-only with respect to execution. No order placement or strategy state mutation.
"""

from __future__ import annotations

import collections
import enum
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


class CandidateEmptyClass(str, enum.Enum):
    NO_MARKET_SETUP = "NO_MARKET_SETUP"
    INPUT_NOT_READY = "INPUT_NOT_READY"
    INPUT_STALE = "INPUT_STALE"
    STRATEGY_NOT_INVOKED = "STRATEGY_NOT_INVOKED"
    ROUTING_FAILURE = "ROUTING_FAILURE"
    STRATEGY_EXCEPTION = "STRATEGY_EXCEPTION"
    STRATEGY_RETURNED_EMPTY = "STRATEGY_RETURNED_EMPTY"
    CANDIDATE_CREATED = "CANDIDATE_CREATED"
    CANDIDATE_FILTERED_LIQUIDITY = "CANDIDATE_FILTERED_LIQUIDITY"
    CANDIDATE_FILTERED_RISK = "CANDIDATE_FILTERED_RISK"
    CANDIDATE_FILTERED_GOVERNANCE = "CANDIDATE_FILTERED_GOVERNANCE"
    CANDIDATE_FILTERED_FRESHNESS = "CANDIDATE_FILTERED_FRESHNESS"
    CANDIDATE_FILTERED_REGIME = "CANDIDATE_FILTERED_REGIME"
    CANDIDATE_FILTERED_OTHER = "CANDIDATE_FILTERED_OTHER"
    RANKING_DROPPED = "RANKING_DROPPED"
    PERSISTENCE_OR_SERIALIZATION_FAILURE = "PERSISTENCE_OR_SERIALIZATION_FAILURE"
    UNKNOWN = "UNKNOWN"


class EmptyPoolSummaryClass(str, enum.Enum):
    LEGITIMATE_NO_SETUP = "LEGITIMATE_NO_SETUP"
    INPUT_READINESS_PROBLEM = "INPUT_READINESS_PROBLEM"
    WIRING_PROBLEM = "WIRING_PROBLEM"
    DOWNSTREAM_FILTERING = "DOWNSTREAM_FILTERING"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class CandidateLifecycleStage(str, enum.Enum):
    CREATED = "CREATED"
    LIQUIDITY_CHECK = "LIQUIDITY_CHECK"
    FRESHNESS_CHECK = "FRESHNESS_CHECK"
    REGIME_CHECK = "REGIME_CHECK"
    RISK_CHECK = "RISK_CHECK"
    GOVERNANCE_CHECK = "GOVERNANCE_CHECK"
    RANKING = "RANKING"
    ADVISORY = "ADVISORY"


@dataclass(frozen=True)
class StrategyEvaluationAttribution:
    """Attribution for a single strategy's evaluation during a cycle."""

    strategy_id: str
    invoked: bool
    input_ready: bool
    input_fresh: bool
    evaluation_status: str
    candidate_count_before_filters: int
    candidate_count_after_filters: int
    candidate_count_after_risk: int
    candidate_count_after_ranking: int
    terminal_reason_code: str
    is_order_action: bool = False  # is_order_action=false
    broker_write_authority: bool = False

    def validate(self) -> None:
        if not str(self.strategy_id).strip():
            raise ValueError("strategy_id_required")
        if self.terminal_reason_code not in {c.value for c in CandidateEmptyClass}:
            raise ValueError(f"invalid_terminal_reason_code: {self.terminal_reason_code}")
        if self.is_order_action:  # is_order_action=false
            raise ValueError("attribution_order_action_forbidden")
        if self.broker_write_authority:
            raise ValueError("attribution_broker_write_forbidden")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_order_action"] = False
        data["broker_write_authority"] = False
        return data


@dataclass
class StrategyMetricsRecord:
    """Accumulated performance and evaluation counters for a strategy."""

    strategy_id: str
    enabled: bool = True
    wired: bool = True
    invoked_since_last_report: bool = False
    evaluation_count: int = 0
    valid_input_count: int = 0
    empty_result_count: int = 0
    candidate_emission_count: int = 0
    filtered_count: int = 0
    blocked_count: int = 0
    exception_count: int = 0
    last_reason_code: str = CandidateEmptyClass.UNKNOWN.value
    last_evaluation_ts: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateTransitionRecord:
    """Immutable record of a candidate transition across a pipeline stage."""

    candidate_id: str
    from_stage: str
    to_stage: str
    status: str  # PASS | FILTERED | BLOCKED | DROPPED
    reason_code: str
    timestamp: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    is_order_action: bool = False  # is_order_action=false
    broker_write_authority: bool = False

    def validate(self) -> None:
        if not str(self.candidate_id).strip():
            raise ValueError("candidate_id_required")
        if not str(self.from_stage).strip() or not str(self.to_stage).strip():
            raise ValueError("stages_required")
        if self.is_order_action:  # is_order_action=false
            raise ValueError("candidate_transition_order_action_forbidden")
        if self.broker_write_authority:
            raise ValueError("candidate_transition_broker_write_forbidden")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["metadata"] = dict(self.metadata)
        data["is_order_action"] = False
        data["broker_write_authority"] = False
        return data


class CandidateLifecycleLedger:
    """Ledger tracking candidate lifecycles to detect silent drops and explain filtration."""

    def __init__(self, maxlen: int = 2000) -> None:
        self.maxlen = maxlen
        # candidate_id -> list of transitions
        self._transitions: collections.OrderedDict[str, list[CandidateTransitionRecord]] = collections.OrderedDict()
        self._terminal_states: dict[str, str] = {}

    def record_transition(
        self,
        *,
        candidate_id: str,
        from_stage: str | CandidateLifecycleStage,
        to_stage: str | CandidateLifecycleStage,
        status: str,
        reason_code: str,
        timestamp: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CandidateTransitionRecord:
        now_iso = timestamp or datetime.now(timezone.utc).isoformat()
        f_stage = from_stage.value if isinstance(from_stage, CandidateLifecycleStage) else str(from_stage)
        t_stage = to_stage.value if isinstance(to_stage, CandidateLifecycleStage) else str(to_stage)

        record = CandidateTransitionRecord(
            candidate_id=str(candidate_id),
            from_stage=f_stage,
            to_stage=t_stage,
            status=str(status),
            reason_code=str(reason_code),
            timestamp=now_iso,
            metadata=dict(metadata or {}),
            is_order_action=False,
            broker_write_authority=False,
        )
        record.validate()

        cid = record.candidate_id
        if cid not in self._transitions:
            if len(self._transitions) >= self.maxlen:
                self._transitions.popitem(last=False)
            self._transitions[cid] = []

        self._transitions[cid].append(record)
        self._terminal_states[cid] = record.status
        return record

    def get_candidate_history(self, candidate_id: str) -> list[CandidateTransitionRecord]:
        return list(self._transitions.get(candidate_id, []))

    def detect_disappeared_candidates(self, expected_stage: str = CandidateLifecycleStage.ADVISORY.value) -> list[dict[str, Any]]:
        """Identify candidates that stopped transitioning before terminal advisory stage without explicit terminal status."""
        disappeared: list[dict[str, Any]] = []
        for cid, transitions in self._transitions.items():
            if not transitions:
                continue
            last = transitions[-1]
            if last.to_stage != expected_stage and last.status == "PASS":
                # Candidate passed last stage but was never seen at subsequent stages
                disappeared.append({
                    "candidate_id": cid,
                    "last_stage": last.to_stage,
                    "last_status": last.status,
                    "last_reason": last.reason_code,
                    "last_ts": last.timestamp,
                    "possible_defect": "SILENT_CANDIDATE_DROP_BEFORE_DOWNSTREAM_STAGE",
                })
        return disappeared


class StrategyCoverageTracker:
    """Maintains strategy matrix and empty candidate pool attribution."""

    def __init__(self, registered_strategies: Sequence[str] | None = None) -> None:
        self._strategies: dict[str, StrategyMetricsRecord] = {}
        if registered_strategies:
            for s_id in registered_strategies:
                self.register_strategy(s_id)
        self._attributions: collections.deque[StrategyEvaluationAttribution] = collections.deque(maxlen=1000)

    def register_strategy(self, strategy_id: str, enabled: bool = True, wired: bool = True) -> None:
        s_id = str(strategy_id).strip()
        if s_id not in self._strategies:
            self._strategies[s_id] = StrategyMetricsRecord(strategy_id=s_id, enabled=enabled, wired=wired)

    def record_evaluation(self, attribution: StrategyEvaluationAttribution) -> None:
        attribution.validate()
        s_id = attribution.strategy_id
        if s_id not in self._strategies:
            self.register_strategy(s_id)

        rec = self._strategies[s_id]
        rec.invoked_since_last_report = True
        rec.evaluation_count += 1
        rec.last_reason_code = attribution.terminal_reason_code
        rec.last_evaluation_ts = datetime.now(timezone.utc).isoformat()

        if attribution.input_ready and attribution.input_fresh:
            rec.valid_input_count += 1

        if attribution.candidate_count_before_filters == 0:
            rec.empty_result_count += 1
        else:
            rec.candidate_emission_count += attribution.candidate_count_before_filters

        filtered = max(0, attribution.candidate_count_before_filters - attribution.candidate_count_after_filters)
        rec.filtered_count += filtered

        blocked = max(0, attribution.candidate_count_after_filters - attribution.candidate_count_after_risk)
        rec.blocked_count += blocked

        if attribution.terminal_reason_code == CandidateEmptyClass.STRATEGY_EXCEPTION.value:
            rec.exception_count += 1

        self._attributions.append(attribution)

    def get_strategy_matrix(self) -> dict[str, Any]:
        records = [rec.to_dict() for rec in self._strategies.values()]
        total_expected = len(self._strategies)
        wired_count = sum(1 for s in self._strategies.values() if s.wired)
        invoked_count = sum(1 for s in self._strategies.values() if s.invoked_since_last_report)
        valid_input_count = sum(1 for s in self._strategies.values() if s.valid_input_count > 0)
        emitting_count = sum(1 for s in self._strategies.values() if s.candidate_emission_count > 0)

        return {
            "strategies": records,
            "summary": {
                "STRATEGIES_EXPECTED": total_expected,
                "STRATEGIES_WIRED": wired_count,
                "STRATEGIES_INVOKED": invoked_count,
                "STRATEGIES_WITH_VALID_INPUT": valid_input_count,
                "STRATEGIES_EMITTING_CANDIDATES": emitting_count,
            },
        }

    def reset_report_interval_flags(self) -> None:
        for s in self._strategies.values():
            s.invoked_since_last_report = False

    def diagnose_empty_pool(self, recent_window_cycles: int = 10) -> dict[str, Any]:
        """Diagnose why the candidate pool is empty across recent evaluations."""
        recent = list(self._attributions)[-max(1, recent_window_cycles) :]
        if not recent:
            return {
                "CANDIDATE_POOL_EMPTY": True,
                "EMPTY_POOL_CLASS": EmptyPoolSummaryClass.UNKNOWN.value,
                "STRATEGY_EVALUATIONS": 0,
                "VALID_INPUT_EVALUATIONS": 0,
                "NO_MARKET_SETUP": 0,
                "NOT_INVOKED": 0,
                "INPUT_STALE": 0,
                "ROUTING_FAILURE": 0,
                "FILTERED": 0,
                "ERRORS": 0,
            }

        eval_count = len(recent)
        valid_input = sum(1 for a in recent if a.input_ready and a.input_fresh)
        no_setup = sum(1 for a in recent if a.terminal_reason_code == CandidateEmptyClass.NO_MARKET_SETUP.value)
        not_invoked = sum(1 for a in recent if not a.invoked or a.terminal_reason_code == CandidateEmptyClass.STRATEGY_NOT_INVOKED.value)
        stale = sum(1 for a in recent if a.terminal_reason_code == CandidateEmptyClass.INPUT_STALE.value)
        routing = sum(1 for a in recent if a.terminal_reason_code == CandidateEmptyClass.ROUTING_FAILURE.value)
        errors = sum(1 for a in recent if a.terminal_reason_code == CandidateEmptyClass.STRATEGY_EXCEPTION.value)
        filtered = sum(
            1
            for a in recent
            if a.terminal_reason_code.startswith("CANDIDATE_FILTERED") or a.terminal_reason_code == CandidateEmptyClass.RANKING_DROPPED.value
        )

        # Classify the pool state
        if not_invoked > 0 or routing > 0:
            classification = EmptyPoolSummaryClass.WIRING_PROBLEM.value
        elif stale > 0 or (valid_input == 0 and eval_count > 0):
            classification = EmptyPoolSummaryClass.INPUT_READINESS_PROBLEM.value
        elif filtered > 0 and no_setup == 0:
            classification = EmptyPoolSummaryClass.DOWNSTREAM_FILTERING.value
        elif no_setup == eval_count and valid_input == eval_count:
            classification = EmptyPoolSummaryClass.LEGITIMATE_NO_SETUP.value
        else:
            classification = EmptyPoolSummaryClass.MIXED.value

        return {
            "CANDIDATE_POOL_EMPTY": True,
            "EMPTY_POOL_CLASS": classification,
            "STRATEGY_EVALUATIONS": eval_count,
            "VALID_INPUT_EVALUATIONS": valid_input,
            "NO_MARKET_SETUP": no_setup,
            "NOT_INVOKED": not_invoked,
            "INPUT_STALE": stale,
            "ROUTING_FAILURE": routing,
            "FILTERED": filtered,
            "ERRORS": errors,
        }
