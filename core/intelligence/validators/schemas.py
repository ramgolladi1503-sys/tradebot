from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class EvidenceValue:
    """Every extracted field must be traceable via this envelope."""
    value: Any
    origin: str
    evidence_pointer: str
    confidence: float
    reason: str
    parser_version: str
    status: str  # 'measured', 'configured', 'inferred', 'calibrated'

@dataclass
class ExtractionEvent:
    """The normalized output schema for an extracted intelligence event."""
    title: EvidenceValue
    source_url: EvidenceValue
    published_timestamp: Optional[EvidenceValue]
    fetched_timestamp: EvidenceValue
    source_type: EvidenceValue
    source_authority: EvidenceValue
    document_category: EvidenceValue
    event_type: EvidenceValue
    named_entities: EvidenceValue
    affected_index: Optional[EvidenceValue]
    raw_excerpt_pointers: EvidenceValue
    parser_version: str
    extraction_version: str

    # Crucially, we omit market_relevance and trading_impact per Agent 5 instructions.
    # Those are strictly handled by Calibration/Replay downstream.
