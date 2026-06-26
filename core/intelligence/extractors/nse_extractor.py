import re
import time
from typing import Dict, Any
from core.intelligence.extractors.hardened_base import HardenedBaseExtractor, ExtractionError

class NSEExtractor(HardenedBaseExtractor):
    """
    Source-specific extractor for NSE Circulars and Notices.
    """
    PARSER_VERSION = "1.0.0"
    
    def _extract_specifics(self, normalized_text: str) -> Dict[str, Any]:
        parsed = {}
        
        # NSE typically uses "Circular No:" or "Subject:"
        title_match = re.search(r'(?:subject|circular no)[:\-]?\s*(.{10,200}?)(\.|$|\n)', normalized_text, re.IGNORECASE)
        if title_match:
            parsed["title"] = title_match.group(1).strip()
        else:
            raise ExtractionError("Missing title in NSE document")
            
        # Parse Dates (e.g. "DD-MMM-YYYY")
        ts_match = re.search(r'(?:date)[:\-]?\s*(\d{2}-[A-Za-z]{3}-\d{4})', normalized_text, re.IGNORECASE)
        if ts_match:
            date_str = ts_match.group(1).strip()
            try:
                parsed["published_timestamp"] = time.mktime(time.strptime(date_str, "%d-%b-%Y"))
            except ValueError:
                pass
            
        parsed["metadata"] = {"source_domain": "nseindia.com", "category": "exchange_circular"}
        
        return parsed
