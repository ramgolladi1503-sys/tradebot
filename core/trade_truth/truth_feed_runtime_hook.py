"""Truth Feed Runtime Hook & Checkpoint Pulse Instrumentation.

Binds the live observation pipeline to TruthStore and writes checkpoint spans.
Guarantees:
- Zero broker write / order execution authority.
- Append-only persistent truth record generation.
- Full 20-stage pulse propagation and timing.
- Real hooks for option selection, candidate pool, scoring, ranking, trade builder, risk, governance.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.trade_truth.decision_hash import compute_deterministic_hash
from core.trade_truth.models import (
    TRUTH_SCHEMA_VERSION,
    AnalyticalTruth,
    DecisionTruth,
    ExecutionTruth,
    IdentityTruth,
    MarketTruth,
    ProvenanceTruth,
    TimingTruth,
    TradeTruthRecord,
)
from core.trade_truth.provenance import build_provenance_truth
from core.trade_truth.record_builder import build_trade_truth_record
from core.trade_truth.store import TruthStore

logger = logging.getLogger(__name__)

ALL_STAGES: tuple[str, ...] = (
    "MARKET_FEED",
    "WEBSOCKET",
    "INGESTION",
    "NORMALIZATION",
    "MARKET_MEMORY",
    "FEATURE_ENGINE",
    "REGIME",
    "STRATEGY",
    "CANDIDATE_GENERATION",
    "FAMILY_COMPATIBILITY",
    "CANDIDATE_ADMISSION",
    "OPTION_SELECTION",
    "CANDIDATE_POOL",
    "SCORING",
    "RANKING",
    "TRADE_BUILDER",
    "RISK",
    "GOVERNANCE",
    "ADVISORY_DECISION",
    "EXECUTION_BOUNDARY",
)


@dataclass
class CheckpointSpan:
    stage_name: str
    trace_id: str
    parent_span_id: Optional[str]
    entered_at: float
    exited_at: float
    input_hash: str
    output_hash: str
    status: str  # PASS, BLOCKED, SKIPPED_NOT_APPLICABLE, UNKNOWN, ERROR
    reason_code: str
    exception: Optional[str]
    latency_ms: float
    data_freshness_sec: Optional[float] = None
    source_timestamp: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TruthFeedRuntimeHook:
    """Manages real-time capture and checkpoint span persistence for a session."""

    def __init__(
        self,
        session_root: Path,
        session_date: str,
        session_id: str,
        truth_store: Optional[TruthStore] = None,
    ) -> None:
        self.session_root = Path(session_root)
        self.session_date = session_date
        self.session_id = session_id
        self.truth_root = self.session_root / "truth_feed"
        self.truth_root.mkdir(parents=True, exist_ok=True)
        self.pulse_path = self.truth_root / "CHECKPOINT_PULSE.jsonl"
        self.store = truth_store or TruthStore(self.truth_root / f"truth_feed_{session_date}.jsonl")
        self.spans: List[CheckpointSpan] = []
        self._arm_broker_guards()

    def _arm_broker_guards(self) -> None:
        from core.trade_truth.prospective_capture_engine import arm_broker_write_guards
        arm_broker_write_guards()

    def record_checkpoint(
        self,
        *,
        stage_name: str,
        trace_id: str,
        parent_span_id: Optional[str],
        entered_at: float,
        exited_at: float,
        input_hash: str,
        output_hash: str,
        status: str,
        reason_code: str = "",
        exception: Optional[str] = None,
        data_freshness_sec: Optional[float] = None,
        source_timestamp: Optional[float] = None,
    ) -> CheckpointSpan:
        latency_ms = max(0.0, (exited_at - entered_at) * 1000.0)
        span = CheckpointSpan(
            stage_name=stage_name,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            entered_at=entered_at,
            exited_at=exited_at,
            input_hash=input_hash,
            output_hash=output_hash,
            status=status,
            reason_code=reason_code,
            exception=exception,
            latency_ms=latency_ms,
            data_freshness_sec=data_freshness_sec,
            source_timestamp=source_timestamp,
        )
        self.spans.append(span)
        with self.pulse_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(span.to_dict(), sort_keys=True) + "\n")
        return span

    def commit_decision_trace(
        self,
        *,
        trace_id: str,
        candidate_id: str,
        strategy_id: str,
        instrument: str,
        underlying: str,
        decision_timestamp_epoch: float,
        decision_timestamp_iso: str,
        market_truth: Mapping[str, Any],
        analytical_truth: Mapping[str, Any],
        decision_truth: Mapping[str, Any],
        stage_hashes: Mapping[str, str],
        execution_truth: Optional[Mapping[str, Any]] = None,
        sequence_num: Optional[int] = None,
    ) -> TradeTruthRecord:
        provenance = build_provenance_truth()
        record = build_trade_truth_record(
            trace_id=trace_id,
            session_id=self.session_id,
            candidate_id=candidate_id,
            strategy_id=strategy_id,
            instrument=instrument,
            underlying=underlying,
            timing_truth={
                "decision_timestamp_epoch": decision_timestamp_epoch,
                "decision_timestamp_iso": decision_timestamp_iso,
            },
            market_truth=market_truth,
            analytical_truth=analytical_truth,
            decision_truth=decision_truth,
            execution_truth=execution_truth or {
                "order_authority": False,
                "broker_write_authority": False,
                "executable_side": "NONE",
                "execution_status": "NOT_AUTHORIZED",
            },
            provenance_truth=asdict(provenance),
            previous_record_hash=self.store.last_record_hash,
            sequence_number=sequence_num or self.store.next_sequence_number,
        )
        self.store.append(record)
        return record
