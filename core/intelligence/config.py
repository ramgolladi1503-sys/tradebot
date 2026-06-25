from dataclasses import dataclass
from typing import Optional, Dict

@dataclass
class MIPConfig:
    """Configuration for Market Intelligence Platform"""
    # Feature Flags
    ENABLE_MIP: bool = True
    
    # Execution Rules - MUST NEVER CHANGE
    ALLOW_EXECUTION_INFLUENCE: bool = False
    ALLOW_RANKING_INFLUENCE: bool = False
    
    # Limits
    MAX_RETRIES: int = 3
    RATE_LIMIT_DELAY_SECONDS: float = 2.0
    
    # Store settings
    EVIDENCE_DIR: str = "logs/mip_evidence"
    RAW_DIR: str = "logs/mip_raw"

    # API Keys (loaded via env, mapped here)
    FIRECRAWL_API_KEY: Optional[str] = None

# Global config instance
config = MIPConfig()
