import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
from core.intelligence.robots_gate import RobotsGate
from core.intelligence.config import config

logger = logging.getLogger(__name__)

class CircuitBreakerOpen(Exception):
    pass

class FetchFailureReason(ABC):
    ROBOTS_BLOCKED = "robots_blocked"
    TIMEOUT = "timeout"
    SIZE_EXCEEDED = "size_exceeded"
    INVALID_CONTENT_TYPE = "invalid_content_type"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    HTTP_ERROR = "http_error"
    SOURCE_DISABLED = "source_disabled"

class BaseFetcher(ABC):
    """
    WHY IT EXISTS: To safely isolate TradeBot from the public internet using exponential backoff, circuit breakers, and payload caps.
    WHEN TO USE IT: Used to wrap all external HTTP or API requests.
    LIMITATIONS: Currently synchronous. Blocks the thread (which is why it must run out-of-band in `run_intelligence_pipeline.py`).
    CALIBRATION STATUS: N/A. Only fetches bytes.
    EXECUTION INFLUENCE: NONE.
    
    ARCHITECTURAL ROLE: Network edge defense. Enforces backoffs, timeouts, size limits, and circuit breakers.
    DEPENDENCIES: `urllib.request`, `RobotsGate`.
    EXTENSION POINTS: Subclasses implement `_execute_fetch()`.
    """
    def __init__(self, source_id: str, user_agent: str = "TradeBotIntelligence/1.0"):
        self.source_id = source_id
        self.robots_gate = RobotsGate(user_agent=user_agent)
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self._disabled = False

    def disable_source(self):
        self._disabled = True

    def _check_circuit_breaker(self) -> None:
        if self._disabled:
            raise CircuitBreakerOpen(FetchFailureReason.SOURCE_DISABLED)

        if self.consecutive_failures >= config.fetcher.CIRCUIT_BREAKER_FAILURE_THRESHOLD:
            elapsed = time.time() - self.last_failure_time
            if elapsed < config.fetcher.CIRCUIT_BREAKER_RECOVERY_SECONDS:
                raise CircuitBreakerOpen(FetchFailureReason.CIRCUIT_BREAKER_OPEN)
            else:
                # Half-open state
                self.consecutive_failures = config.fetcher.CIRCUIT_BREAKER_FAILURE_THRESHOLD - 1

    def fetch(self, url: str) -> Tuple[Optional[Dict[str, Any]], str, float]:
        """
        Returns: (Payload, FailureReason/Status, Latency)
        """
        start_time = time.time()

        try:
            self._check_circuit_breaker()
        except CircuitBreakerOpen as e:
            logger.warning(f"Circuit breaker prevents fetching {url}: {e}")
            return None, str(e), 0.0

        if not self.robots_gate.can_fetch(url):
            self._record_failure()
            latency = time.time() - start_time
            return None, FetchFailureReason.ROBOTS_BLOCKED, latency

        backoff = config.fetcher.INITIAL_BACKOFF_SECONDS

        for attempt in range(config.fetcher.MAX_RETRIES):
            try:
                result = self._execute_fetch(url)

                # Check response size and type if the subclass implemented it within result
                if result.get("size_bytes", 0) > config.fetcher.MAX_RESPONSE_SIZE_BYTES:
                    self._record_failure()
                    return None, FetchFailureReason.SIZE_EXCEEDED, time.time() - start_time

                content_type = result.get("content_type", "")
                if content_type and not any(ct in content_type for ct in config.fetcher.ALLOWED_CONTENT_TYPES):
                    self._record_failure()
                    return None, FetchFailureReason.INVALID_CONTENT_TYPE, time.time() - start_time

                self._record_success()
                return result, "success", time.time() - start_time

            except Exception as e:
                logger.warning(f"Fetch attempt {attempt+1} failed for {url}: {e}")
                if attempt == config.fetcher.MAX_RETRIES - 1:
                    self._record_failure()
                    return None, FetchFailureReason.HTTP_ERROR, time.time() - start_time

                time.sleep(backoff)
                backoff = min(backoff * config.fetcher.BACKOFF_MULTIPLIER, config.fetcher.MAX_BACKOFF_SECONDS)

        self._record_failure()
        return None, FetchFailureReason.TIMEOUT, time.time() - start_time

    def _record_success(self):
        self.consecutive_failures = 0

    def _record_failure(self):
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

    @abstractmethod
    def _execute_fetch(self, url: str) -> Dict[str, Any]:
        """
        Must return dict containing: 'raw_content', 'status', 'size_bytes', 'content_type'.
        """
        pass
