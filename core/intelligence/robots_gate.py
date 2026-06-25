import time
import urllib.robotparser
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class RobotsGate:
    """
    Standard library-only robots.txt gate.
    Reads robots.txt, respects disallows (fail closed if unreadable or disallowed),
    and honors crawl delays.
    """
    def __init__(self, user_agent: str = "TradeBotIntelligence/1.0"):
        self.user_agent = user_agent
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request_time: dict[str, float] = {}

    def _get_parser(self, netloc: str, scheme: str) -> urllib.robotparser.RobotFileParser:
        if netloc not in self._parsers:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = f"{scheme}://{netloc}/robots.txt"
            rp.set_url(robots_url)
            try:
                rp.read()
            except Exception as e:
                logger.warning(f"Failed to read robots.txt from {robots_url}: {e}. Failing closed.")
                # By leaving it un-read, can_fetch will default to false in some implementations, 
                # but we will handle it explicitly below.
            self._parsers[netloc] = rp
        return self._parsers[netloc]

    def can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched and execute mandatory crawl delay wait."""
        parsed = urlparse(url)
        if not parsed.netloc:
            return False

        rp = self._get_parser(parsed.netloc, parsed.scheme)
        
        # If robots.txt was not found or is empty, we fail closed for safety.
        # But if it's legally empty or fully permissive, can_fetch is True.
        # urllib handles the parsing rules.
        try:
            if not rp.can_fetch(self.user_agent, url):
                logger.warning(f"Robots.txt disallowed fetch for {url}")
                return False
        except Exception:
             # Fail closed on any parser error
             return False

        # Handle crawl delay
        delay = rp.crawl_delay(self.user_agent)
        if delay:
            last_req = self._last_request_time.get(parsed.netloc, 0.0)
            now = time.time()
            elapsed = now - last_req
            if elapsed < delay:
                wait_time = delay - elapsed
                logger.debug(f"Honoring crawl delay of {delay}s for {parsed.netloc}. Sleeping {wait_time:.2f}s.")
                time.sleep(wait_time)
        
        self._last_request_time[parsed.netloc] = time.time()
        return True
