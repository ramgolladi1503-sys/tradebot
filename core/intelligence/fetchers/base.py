from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from core.intelligence.robots_gate import RobotsGate
import logging

logger = logging.getLogger(__name__)

class BaseFetcher(ABC):
    """
    Abstract base fetcher ensuring robots.txt and graceful failure.
    """
    def __init__(self, user_agent: str = "TradeBotIntelligence/1.0"):
        self.robots_gate = RobotsGate(user_agent=user_agent)

    def fetch(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the URL, returning a dict with raw data or None if blocked/failed.
        Must respect robots.txt.
        """
        if not self.robots_gate.can_fetch(url):
            logger.warning(f"Fetch blocked by robots.txt or rate limit for {url}")
            return None
            
        try:
            return self._execute_fetch(url)
        except Exception as e:
            logger.error(f"Fetch execution failed for {url}: {e}")
            return None

    @abstractmethod
    def _execute_fetch(self, url: str) -> Dict[str, Any]:
        """Subclass implementation of the actual fetch."""
        pass
