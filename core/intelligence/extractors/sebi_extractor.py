import re
import time
from typing import Dict, Any
from core.intelligence.extractors.hardened_base import HardenedBaseExtractor, ExtractionError

class SEBIExtractor(HardenedBaseExtractor):
    """
    Source-specific extractor for SEBI Circulars and Orders.
    """
    PARSER_VERSION = "1.0.0"
    
    def _extract_specifics(self, normalized_text: str) -> Dict[str, Any]:
        parsed = {}
        
        # SEBI usually formats titles prominently.
        title_match = re.search(r'(?:subject|title|circular)[:\-]?\s*(.{10,200}?)(\.|$|\n)', normalized_text, re.IGNORECASE)
        if title_match:
            parsed["title"] = title_match.group(1).strip()
        else:
            raise ExtractionError("Missing title in SEBI document")
            
        # Parse Dates (e.g. "May 01, 2026")
        ts_match = re.search(r'(?:date|dated)[:\-]?\s*([a-zA-Z]{3}\s*\d{1,2},\s*\d{4})', normalized_text, re.IGNORECASE)
        if ts_match:
            date_str = ts_match.group(1).replace(",", "").strip()
            try:
                parsed["published_timestamp"] = time.mktime(time.strptime(date_str, "%b %d %Y"))
            except ValueError:
                pass
            
        parsed["metadata"] = {"source_domain": "sebi.gov.in", "category": "regulatory_circular"}
        
        return parsed
