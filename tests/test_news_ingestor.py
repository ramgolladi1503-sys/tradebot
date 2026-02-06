from core.news_ingestor import ingest_headlines, _parse_rss


RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0">
<channel>
  <title>Sample</title>
  <item>
    <title>RBI surprises with rate hike</title>
    <pubDate>Thu, 05 Feb 2026 06:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Budget expectations lift markets</title>
    <pubDate>Thu, 05 Feb 2026 05:00:00 GMT</pubDate>
  </item>
</channel>
</rss>
"""


def test_parse_rss():
    rows = _parse_rss(RSS_SAMPLE, "example.com")
    assert len(rows) == 2
    assert rows[0].source == "example.com"


def test_ingest_headlines_dedup():
    def fetcher(_):
        return RSS_SAMPLE
    headlines = ingest_headlines(["https://example.com/rss"], fetcher=fetcher)
    assert len(headlines) == 2
