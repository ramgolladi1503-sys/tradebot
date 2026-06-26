from dataclasses import dataclass
from typing import List
from datetime import date
from core.strategy_registry.registry_types import (
    ImplementationStatus,
    ReplayStatus,
    CertificationStatus,
    PaperValidationStatus,
    AuditStatus,
    ProductionStatus,
)


@dataclass(frozen=True)
class StrategyContract:
    strategy_id: str
    strategy_name: str
    version: str
    owner: str
    created_date: date
    description: str
    market_hypothesis: str
    primary_market: str
    supported_indices: List[str]
    supported_option_types: List[str]

    entry_rules_summary: str
    exit_rules_summary: str
    stop_logic_summary: str
    target_logic_summary: str
    time_stop: str

    required_indicators: List[str]
    required_market_data: List[str]
    required_option_data: List[str]
    required_sessions: List[str]
    required_liquidity: str

    allowed_regimes: List[str]
    forbidden_regimes: List[str]
    required_confirmations: List[str]

    known_limitations: List[str]
    known_assumptions: List[str]

    implementation_status: ImplementationStatus = ImplementationStatus.UNKNOWN
    audit_status: AuditStatus = AuditStatus.UNAUDITED
    replay_status: ReplayStatus = ReplayStatus.NOT_RUN
    certification_status: CertificationStatus = CertificationStatus.NOT_STARTED
    paper_validation_status: PaperValidationStatus = PaperValidationStatus.NOT_STARTED
    production_status: ProductionStatus = ProductionStatus.NOT_APPROVED
