"""Trade Truth Subsystem — Market-to-Decision-to-Execution-to-Outcome Truth.

Guarantees:
- Read-only: broker_api_called=False, is_order_action=False.
- Immutable records with cryptographic chain integrity verification.
- Deterministic Live Decision Hash with Replay Parity.
- Fail-closed forensics.
"""

from core.trade_truth.models import (
    TradeTruthRecord,
    IdentityTruth,
    TimingTruth,
    MarketTruth,
    AnalyticalTruth,
    DecisionTruth,
    ProvenanceTruth,
    ExecutionTruth,
    OutcomeTruth,
    TRUTH_SCHEMA_VERSION,
    TRUTH_SOURCE,
    TRUTH_INCOMPLETE,
    TRUTH_CORRUPT,
    TRUTH_SCHEMA_MISMATCH,
    TRUTH_SEQUENCE_GAP,
    TRUTH_STALE,
    REPLAY_DIVERGENCE,
    FORENSIC_DIVERGENCE,
    EXECUTION_TRUTH_UNKNOWN,
)
from core.trade_truth.decision_hash import (
    compute_live_decision_hash,
    compute_record_integrity_hash,
)
from core.trade_truth.record_builder import build_trade_truth_record
from core.trade_truth.store import TruthStore, default_partitioned_truth_path, TruthStoreError
from core.trade_truth.replay import replay_truth_record, ReplayResult, default_decision_evaluator
from core.trade_truth.outcome_collector import (
    compute_horizons_mfe_mae,
    attach_outcome_amendment,
    PricePoint,
)
from core.trade_truth.session_report import generate_session_truth_report
from core.trade_truth.decay_watchdog import evaluate_strategy_decay, DecayEvaluation

__all__ = [
    "TradeTruthRecord",
    "IdentityTruth",
    "TimingTruth",
    "MarketTruth",
    "AnalyticalTruth",
    "DecisionTruth",
    "ProvenanceTruth",
    "ExecutionTruth",
    "OutcomeTruth",
    "TRUTH_SCHEMA_VERSION",
    "TRUTH_SOURCE",
    "TRUTH_INCOMPLETE",
    "TRUTH_CORRUPT",
    "TRUTH_SCHEMA_MISMATCH",
    "TRUTH_SEQUENCE_GAP",
    "TRUTH_STALE",
    "REPLAY_DIVERGENCE",
    "FORENSIC_DIVERGENCE",
    "EXECUTION_TRUTH_UNKNOWN",
    "compute_live_decision_hash",
    "compute_record_integrity_hash",
    "build_trade_truth_record",
    "TruthStore",
    "default_partitioned_truth_path",
    "TruthStoreError",
    "replay_truth_record",
    "ReplayResult",
    "default_decision_evaluator",
    "compute_horizons_mfe_mae",
    "attach_outcome_amendment",
    "PricePoint",
    "generate_session_truth_report",
    "evaluate_strategy_decay",
    "DecayEvaluation",
]
