import urllib.request
from typing import Dict, Any
from core.intelligence.fetchers.base import BaseFetcher

class HTTPFetcher(BaseFetcher):
    """
    Standard library HTTP fetcher.
    """
    def _execute_fetch(self, url: str) -> Dict[str, Any]:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': self.robots_gate.user_agent}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8')
            return {
                "raw_content": content,
                "status": response.status,
                "url": url
            }
