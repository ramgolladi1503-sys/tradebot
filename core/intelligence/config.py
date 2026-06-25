from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class FetcherConfig:
    """Production-grade fetcher configuration without magic constants."""
    MAX_RETRIES: int = 3
    INITIAL_BACKOFF_SECONDS: float = 2.0
    BACKOFF_MULTIPLIER: float = 2.0
    MAX_BACKOFF_SECONDS: float = 30.0
    TIMEOUT_SECONDS: float = 15.0
    MAX_RESPONSE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5MB cap
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_SECONDS: float = 300.0  # 5 minutes
    ALLOWED_CONTENT_TYPES: tuple[str, ...] = ("text/html", "application/json", "text/plain")

@dataclass
class MIPConfig:
    """Configuration for Market Intelligence Platform"""
    ENABLE_MIP: bool = True

    # Execution Rules - MUST NEVER CHANGE
    ALLOW_EXECUTION_INFLUENCE: bool = False
    ALLOW_RANKING_INFLUENCE: bool = False

    fetcher: FetcherConfig = FetcherConfig()

    # Store settings
    EVIDENCE_DIR: str = "logs/mip_evidence"
    RAW_DIR: str = "logs/mip_raw"
    SQLITE_DB_PATH: str = "logs/mip_store.sqlite"

    # API Keys (loaded safely via env, missing keys degrade gracefully)
    FIRECRAWL_API_KEY: Optional[str] = None
    CRAWL4AI_API_KEY: Optional[str] = None

config = MIPConfig()
