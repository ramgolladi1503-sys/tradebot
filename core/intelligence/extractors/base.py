from abc import ABC, abstractmethod
from typing import Any, Optional
from core.intelligence.validators.schemas import ExtractionEvent, EvidenceValue

class BaseExtractor(ABC):
    """
    Abstract base for extracting schema-compliant events from raw fetched content.
    """
    PARSER_VERSION = "1.0.0"
    EXTRACTION_VERSION = "1.0.0"

    @abstractmethod
    def extract(self, raw_content: str, source_url: str) -> Optional[ExtractionEvent]:
        """Convert raw text/html into an ExtractionEvent"""
        pass

    def _build_evidence(self, value: Any, pointer: str, conf: float, reason: str, status: str = "inferred") -> EvidenceValue:
        return EvidenceValue(
            value=value,
            origin=self.__class__.__name__,
            evidence_pointer=pointer,
            confidence=conf,
            reason=reason,
            parser_version=self.PARSER_VERSION,
            status=status
        )
