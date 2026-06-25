import re
import time
from typing import Dict, Any
from core.intelligence.extractors.hardened_base import HardenedBaseExtractor, ExtractionError

class RBIExtractor(HardenedBaseExtractor):
    """
    Source-specific extractor for the Reserve Bank of India (RBI).
    """
    PARSER_VERSION = "1.0.1"

    def _extract_specifics(self, normalized_text: str) -> Dict[str, Any]:
        parsed = {}

        # Example naive extraction logic meant to be replaced with real Regex/NLP safely
        title_match = re.search(r'title[:\-]?\s*(.{10,100}?)(\.|$)', normalized_text, re.IGNORECASE)
        if title_match:
            parsed["title"] = title_match.group(1).strip()
        else:
            raise ExtractionError("Missing title in RBI notification")

        # Optional timestamp
        ts_match = re.search(r'date[:\-]?\s*(\d{4}-\d{2}-\d{2})', normalized_text, re.IGNORECASE)
        if ts_match:
            parsed["published_timestamp"] = time.mktime(time.strptime(ts_match.group(1), "%Y-%m-%d"))

        parsed["metadata"] = {"source_domain": "rbi.org.in", "category": "regulatory_notice"}

        return parsed
