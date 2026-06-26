from typing import Callable, Optional
from dataclasses import dataclass

@dataclass
class IntelligenceSource:
    name: str
    base_url: str
    fetcher_type: str  # 'http', 'playwright', 'firecrawl', 'crawl4ai'
    category: str      # 'regulatory', 'exchange', 'news'
    schema_validator: Optional[Callable[[dict], bool]] = None
    frequency_minutes: int = 60

# Source Registry
SOURCES: dict[str, IntelligenceSource] = {
    "rbi_notifications": IntelligenceSource(
        name="RBI Notifications",
        base_url="https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
        fetcher_type="http",
        category="regulatory",
        frequency_minutes=60
    ),
    "sebi_circulars": IntelligenceSource(
        name="SEBI Circulars",
        base_url="https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=7&smid=0",
        fetcher_type="playwright", # Often heavily JS/captcha protected
        category="regulatory",
        frequency_minutes=120
    ),
    "nse_circulars": IntelligenceSource(
        name="NSE Circulars",
        base_url="https://www.nseindia.com/companies-listing/circulars",
        fetcher_type="crawl4ai",
        category="exchange",
        frequency_minutes=30
    )
}
