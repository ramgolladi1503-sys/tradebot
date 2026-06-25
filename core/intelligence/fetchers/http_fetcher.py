import urllib.request
from typing import Dict, Any
from core.intelligence.fetchers.base import BaseFetcher
from core.intelligence.config import config

class HTTPFetcher(BaseFetcher):
    """
    Hardened standard library HTTP fetcher.
    """
    def _execute_fetch(self, url: str) -> Dict[str, Any]:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': self.robots_gate.user_agent}
        )
        with urllib.request.urlopen(req, timeout=config.fetcher.TIMEOUT_SECONDS) as response:
            content_bytes = response.read(config.fetcher.MAX_RESPONSE_SIZE_BYTES + 1)

            return {
                "raw_content": content_bytes.decode('utf-8', errors='ignore'),
                "status": response.status,
                "url": url,
                "size_bytes": len(content_bytes),
                "content_type": response.headers.get('Content-Type', '')
            }
