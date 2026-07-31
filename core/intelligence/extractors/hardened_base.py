import hashlib
import re
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ExtractionError(Exception):
    pass

class HardenedBaseExtractor(ABC):
    """
    WHY IT EXISTS: Provides a robust, version-controlled HTML normalization and routing layer for regulatory document parsing.
    WHEN TO USE IT: Base class for all source-specific extractors (e.g., RBI, SEBI).
    LIMITATIONS: Cannot execute Javascript. Cannot parse PDFs.
    CALIBRATION STATUS: Parsed data is strictly UNCALIBRATED.
    EXECUTION INFLUENCE: Absolutely NONE. Structural enforcement hardcodes market_impact to None.
    
    ARCHITECTURAL ROLE: Transforms raw network bytes into safe, schema-compliant Document dictionaries.
    DEPENDENCIES: Python `re`, `hashlib`. No external ML models.
    EXTENSION POINTS: Subclasses must implement `_extract_specifics()`.
    """
    PARSER_VERSION = "1.0.0"

    def __init__(self, source_domain: str):
        self.source_domain = source_domain

    def normalize_html(self, raw_html: str) -> str:
        """Strips tags and normalizes whitespace."""
        text = re.sub(r'<[^>]+>', ' ', raw_html)
        return ' '.join(text.split())

    def compute_hash(self, raw_content: str) -> str:
        """Deterministic hashing for duplicate detection."""
        return hashlib.md5(raw_content.encode('utf-8'), usedforsecurity=False).hexdigest()

    def canonicalize_link(self, raw_link: str) -> str:
        if raw_link.startswith("http"):
            return raw_link
        return f"https://{self.source_domain}/{raw_link.lstrip('/')}"

    def safe_extract(self, raw_content: str, url: str) -> Dict[str, Any]:
        """Wrapper method enforcing error handling and partial extraction status."""
        doc_hash = self.compute_hash(raw_content)
        normalized = self.normalize_html(raw_content)

        try:
            parsed_data = self._extract_specifics(normalized)
            status = "success"
        except ExtractionError as e:
            logger.warning(f"Partial extraction failure for {url}: {e}")
            parsed_data = {}
            status = "partial_failure"
        except Exception as e:
            logger.error(f"Complete extraction failure for {url}: {e}")
            parsed_data = {}
            status = "failed"

        return {
            "status": status,
            "document_hash": doc_hash,
            "parser_version": self.PARSER_VERSION,
            "url": self.canonicalize_link(url),
            "evidence_pointer": url,
            "title": parsed_data.get("title"),
            "published_timestamp": parsed_data.get("published_timestamp"),
            "metadata": parsed_data.get("metadata", {}),
            # Explicitly blank to force Replay Engine to fill it.
            "market_impact": None,
            "affected_indices": None
        }

    @abstractmethod
    def _extract_specifics(self, normalized_text: str) -> Dict[str, Any]:
        """Subclasses parse out title, timestamp, and metadata."""
        pass
