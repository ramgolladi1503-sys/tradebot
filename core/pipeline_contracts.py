import math
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

class LineageMode(str, Enum):
    REAL_MARKET_DERIVED = "REAL_MARKET_DERIVED"
    REPLAY_DERIVED_PARTIAL = "REPLAY_DERIVED_PARTIAL"
    SYNTHETIC_SHAPE_ONLY = "SYNTHETIC_SHAPE_ONLY"
    MISSING = "MISSING"

class QuoteEvidenceMode(str, Enum):
    REAL_BID_ASK = "REAL_BID_ASK"
    MOCKED_FROM_LTP = "MOCKED_FROM_LTP"
    MISSING = "MISSING"

class BoundaryEvidenceMode(str, Enum):
    ORIGINAL_BOUNDARIES = "ORIGINAL_BOUNDARIES"
    RECONSTRUCTED_BOUNDARIES = "RECONSTRUCTED_BOUNDARIES"
    MISSING_BOUNDARIES = "MISSING_BOUNDARIES"

class ReplayPricePathMode(str, Enum):
    OPTION_BID_ASK_PATH = "OPTION_BID_ASK_PATH"
    OPTION_LTP_PATH = "OPTION_LTP_PATH"
    UNDERLYING_PROXY_PATH = "UNDERLYING_PROXY_PATH"
    MISSING_PRICE_PATH = "MISSING_PRICE_PATH"

class ContractValidationError(ValueError):
    pass

def check_not_null(name: str, value: Any):
    if value is None:
        raise ContractValidationError(f"Field '{name}' cannot be null.")

def check_is_valid_number(name: str, value: Union[float, int]):
    check_not_null(name, value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ContractValidationError(f"Field '{name}' must be a valid number, got {value}.")
    if value < 0 and name in ["ltp", "spot", "quote_truth_ltp", "rr", "quote_freshness_ms"]:
        raise ContractValidationError(f"Field '{name}' cannot be negative, got {value}.")

def check_timestamp(name: str, value: str):
    check_not_null(name, value)
    try:
        # Assuming ISO format strings for timestamps
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ContractValidationError(f"Field '{name}' must be a valid ISO format timestamp, got '{value}'.")

@dataclass
class PipelineObject:
    trace_id: Optional[str] = None
    parent_trace_id: Optional[str] = None
    lineage_mode: LineageMode = LineageMode.MISSING
    quote_evidence_mode: QuoteEvidenceMode = QuoteEvidenceMode.MISSING
    
    def validate_lineage(self):
        # We don't hard-fail if trace_id is missing, but the audit will report it.
        pass

@dataclass
class FeedSnapshot(PipelineObject):
    snapshot_id: str = ""
    symbol: str = ""
    timestamp: str = ""
    spot: float = 0.0
    quote_freshness_ms: int = 0
    
    def validate(self):
        check_not_null("snapshot_id", self.snapshot_id)
        check_not_null("symbol", self.symbol)
        check_timestamp("timestamp", self.timestamp)
        check_is_valid_number("spot", self.spot)
        check_is_valid_number("quote_freshness_ms", self.quote_freshness_ms)

@dataclass
class OptionChainSnapshot(PipelineObject):
    snapshot_id: str = ""
    symbol: str = ""
    timestamp: str = ""
    contracts_resolved: bool = False
    
    def validate(self):
        check_not_null("snapshot_id", self.snapshot_id)
        check_not_null("symbol", self.symbol)
        check_timestamp("timestamp", self.timestamp)
        if not self.contracts_resolved:
            raise ContractValidationError("OptionChainSnapshot must have resolved contracts (contracts_resolved=True).")

@dataclass
class RawSetup(PipelineObject):
    setup_id: str = ""
    symbol: str = ""
    signal_time: str = ""
    setup_type: str = ""
    
    def validate(self):
        check_not_null("setup_id", self.setup_id)
        check_not_null("symbol", self.symbol)
        check_not_null("setup_type", self.setup_type)
        check_timestamp("signal_time", self.signal_time)

@dataclass
class Candidate(PipelineObject):
    candidate_id: str = ""
    strategy: str = ""
    symbol: str = ""
    signal_time: str = ""
    source_snapshot_id: str = ""
    contract_key: Optional[str] = None
    
    # Source evidence fields
    source_timestamp: Optional[str] = None
    quote_timestamp: Optional[str] = None
    quote_age_ms: Optional[int] = None
    spot_ltp: Optional[float] = None
    option_bid: Optional[float] = None
    option_ask: Optional[float] = None
    option_ltp: Optional[float] = None
    expiry: Optional[str] = None
    strike: Optional[float] = None
    option_type: Optional[str] = None
    
    def validate(self):
        check_not_null("candidate_id", self.candidate_id)
        check_not_null("strategy", self.strategy)
        check_not_null("symbol", self.symbol)
        check_timestamp("signal_time", self.signal_time)
        check_not_null("source_snapshot_id", self.source_snapshot_id)
        
        # We enforce evidence fields if we want a FULL PASS in the audit, but the class can just ensure they're valid if present.
        if self.source_timestamp is not None:
            check_timestamp("source_timestamp", self.source_timestamp)
        if self.quote_timestamp is not None:
            check_timestamp("quote_timestamp", self.quote_timestamp)
        if self.quote_age_ms is not None:
            check_is_valid_number("quote_age_ms", self.quote_age_ms)

@dataclass
class GateDecision(PipelineObject):
    decision_id: str = ""
    candidate_id: str = ""
    passed: bool = False
    reject_reason: Optional[str] = None
    blockers: List[str] = field(default_factory=list)
    
    def validate(self):
        check_not_null("decision_id", self.decision_id)
        check_not_null("candidate_id", self.candidate_id)
        if not self.passed and not self.reject_reason and not self.blockers:
            raise ContractValidationError("GateDecision is not passed but missing blocker evidence / reject reason.")

@dataclass
class RankedCandidate(PipelineObject):
    ranking_id: str = ""
    candidate_id: str = ""
    is_executable: bool = False
    is_soft_rejected: bool = False
    has_hard_blockers: bool = False
    quote_truth_fresh: bool = False
    contract_resolved: bool = False
    entry: float = 0.0
    sl: float = 0.0
    target: float = 0.0
    rr: float = 0.0
    
    def validate(self):
        check_not_null("ranking_id", self.ranking_id)
        check_not_null("candidate_id", self.candidate_id)
        
        if self.is_executable:
            if self.has_hard_blockers:
                raise ContractValidationError("Ranked executable candidate cannot have hard blockers.")
            if self.is_soft_rejected:
                raise ContractValidationError("Soft-rejected candidate cannot leak into executable ranking.")
            if not self.quote_truth_fresh:
                raise ContractValidationError("Ranked executable candidate must have fresh quote truth.")
            if not self.contract_resolved:
                raise ContractValidationError("Ranked executable candidate must have resolved contracts.")
            
            check_is_valid_number("entry", self.entry)
            check_is_valid_number("sl", self.sl)
            check_is_valid_number("target", self.target)
            check_is_valid_number("rr", self.rr)
            
            if self.entry <= 0.0 or self.sl <= 0.0 or self.target <= 0.0 or self.rr <= 0.0:
                raise ContractValidationError("Ranked executable candidate must have valid entry, SL, target, and RR > 0.")

@dataclass
class AdvisoryDecision(PipelineObject):
    decision_id: str = ""
    candidate_id: str = ""
    is_executable: bool = False
    
    def validate(self):
        check_not_null("decision_id", self.decision_id)
        check_not_null("candidate_id", self.candidate_id)
        if self.is_executable:
            raise ContractValidationError("Advisory-only candidate cannot be marked executable.")
