"""Read-only TradeBot evidence, analytics, RAG, and certification sidecar."""

from .agent_workflow import ControlledReview, build_langgraph_review, run_controlled_review
from .campaign import CampaignEvidenceSummary, SessionEvidence, summarize_campaign
from .capacity import (
    FillSimulation,
    MarketImpactObservation,
    QueueObservation,
    build_capacity_curve,
    calibrate_queue_fill_probability,
    fit_sqrt_impact_model,
)
from .cas import CASCampaignSummary, CASSessionObservation, summarize_cas_campaign
from .certification import (
    REQUIRED_STRATEGY_GATES,
    CertificationDecision,
    CertificationGateResult,
    GateStatus,
    certify_strategy,
)
from .contracts import CanonicalEvent, EventValidationError
from .costs import CostSchedule, TradeCostInput, calculate_trade_costs
from .counterfactuals import ContractOutcome, blocker_value, compare_contract_counterfactuals
from .drift import diagonal_zscore_ood, jensen_shannon_divergence, ks_statistic, population_stability_index
from .event_graph import MarketEventGraph, MarketEventNode, build_market_event_graph
from .evidence_search import EvidenceDocument, EvidenceIndex
from .feature_parity import FeatureRecord, compare_feature_modes, hash_feature_inputs
from .greek_attribution import GreekSnapshot, attribute_option_pnl
from .market_adapters import market_tick_to_event, option_chain_snapshot_to_events
from .market_analytics import BookLevel, calculate_breadth, calculate_futures_basis, calculate_option_microstructure
from .outcomes import MarketObservation, OutcomeContract, build_causal_outcomes
from .publisher import FileEventPublisher, NoOpEventPublisher
from .rag_ingestion import EvidenceChunk, ingest_evidence_file, plan_evidence_query
from .readiness import CanaryReadiness, evaluate_canary_readiness
from .risk_analytics import RiskSimulation, block_bootstrap_risk
from .runtime_tailer import RuntimeEvidenceTailer, RuntimeTailerConfig
from .safe_publish import NonBlockingPublisher, PublisherStats
from .session import SessionAnalyzer
from .tradebot_adapter import candidate_lineage_to_event, truth_snapshot_to_event
from .validation import LabelInterval, deflated_sharpe_ratio, probability_of_backtest_overfitting, purged_embargoed_splits

__all__ = [
    "REQUIRED_STRATEGY_GATES",
    "BookLevel",
    "CASCampaignSummary",
    "CASSessionObservation",
    "CampaignEvidenceSummary",
    "CanonicalEvent",
    "CanaryReadiness",
    "CertificationDecision",
    "CertificationGateResult",
    "ContractOutcome",
    "ControlledReview",
    "CostSchedule",
    "EventValidationError",
    "EvidenceChunk",
    "EvidenceDocument",
    "EvidenceIndex",
    "FeatureRecord",
    "FileEventPublisher",
    "FillSimulation",
    "GateStatus",
    "GreekSnapshot",
    "LabelInterval",
    "MarketEventGraph",
    "MarketEventNode",
    "MarketImpactObservation",
    "MarketObservation",
    "NoOpEventPublisher",
    "NonBlockingPublisher",
    "OutcomeContract",
    "PublisherStats",
    "QueueObservation",
    "RiskSimulation",
    "RuntimeEvidenceTailer",
    "RuntimeTailerConfig",
    "SessionAnalyzer",
    "SessionEvidence",
    "TradeCostInput",
    "attribute_option_pnl",
    "block_bootstrap_risk",
    "blocker_value",
    "build_capacity_curve",
    "build_causal_outcomes",
    "build_langgraph_review",
    "build_market_event_graph",
    "calculate_breadth",
    "calculate_futures_basis",
    "calculate_option_microstructure",
    "calculate_trade_costs",
    "calibrate_queue_fill_probability",
    "candidate_lineage_to_event",
    "certify_strategy",
    "compare_contract_counterfactuals",
    "compare_feature_modes",
    "deflated_sharpe_ratio",
    "diagonal_zscore_ood",
    "evaluate_canary_readiness",
    "fit_sqrt_impact_model",
    "hash_feature_inputs",
    "ingest_evidence_file",
    "jensen_shannon_divergence",
    "ks_statistic",
    "market_tick_to_event",
    "option_chain_snapshot_to_events",
    "plan_evidence_query",
    "population_stability_index",
    "probability_of_backtest_overfitting",
    "purged_embargoed_splits",
    "run_controlled_review",
    "summarize_campaign",
    "summarize_cas_campaign",
    "truth_snapshot_to_event",
]
