import re
import time
from typing import Dict, Any
from core.intelligence.extractors.hardened_base import HardenedBaseExtractor, ExtractionError

class RBIExtractor(HardenedBaseExtractor):
    """
    Source-specific extractor for the Reserve Bank of India (RBI) Notifications and Press Releases.
    """
    PARSER_VERSION = "2.0.0"
    
    def _extract_specifics(self, normalized_text: str) -> Dict[str, Any]:
        parsed = {}
        
        # RBI typically structures titles after strong/b tags or specific "Press Release :" headers
        # We look for common patterns in RBI text dumps
        title_match = re.search(r'(?:title|press release|notification)[:\-]?\s*(.{10,150}?)(\.|$|\n)', normalized_text, re.IGNORECASE)
        if title_match:
            parsed["title"] = title_match.group(1).strip()
        else:
            raise ExtractionError("Missing title in RBI notification")
            
        # Parse Dates (e.g. "Date : Jan 01, 2026" or "2026-01-01")
        ts_match = re.search(r'(?:date|dated)[:\-]?\s*([a-zA-Z]{3}\s*\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})', normalized_text, re.IGNORECASE)
        if ts_match:
            date_str = ts_match.group(1).replace(",", "").strip()
            try:
                if "-" in date_str:
                    parsed["published_timestamp"] = time.mktime(time.strptime(date_str, "%Y-%m-%d"))
                else:
                    parsed["published_timestamp"] = time.mktime(time.strptime(date_str, "%b %d %Y"))
            except ValueError:
                pass # Gracefully fall back to None
            
        parsed["metadata"] = {"source_domain": "rbi.org.in", "category": "regulatory_notice"}
        
        return parsed
