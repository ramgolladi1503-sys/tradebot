from core.intelligence.extractors.rbi_extractor import RBIExtractor
from core.intelligence.extractors.sebi_extractor import SEBIExtractor
from core.intelligence.extractors.nse_extractor import NSEExtractor

def test_rbi_extractor():
    ext = RBIExtractor("rbi.org.in")
    html = "<html><body>Press Release: The RBI has changed the repo rate. Date: Jan 01, 2026</body></html>"
    res = ext.safe_extract(html, "https://rbi.org.in/test")
    assert res["status"] == "success"
    assert res["title"] == "The RBI has changed the repo rate"
    assert res["published_timestamp"] is not None
    assert res["parser_version"] == "2.0.0"

def test_sebi_extractor():
    ext = SEBIExtractor("sebi.gov.in")
    html = "<html><body>Subject: Master Circular for Brokers. Date: May 01, 2026</body></html>"
    res = ext.safe_extract(html, "https://sebi.gov.in/test")
    assert res["status"] == "success"
    assert res["title"] == "Master Circular for Brokers"
    assert res["published_timestamp"] is not None
    assert res["parser_version"] == "1.0.0"

def test_nse_extractor():
    ext = NSEExtractor("nseindia.com")
    html = "<html><body>Circular No: 12345/2026. Date: 01-May-2026</body></html>"
    res = ext.safe_extract(html, "https://nseindia.com/test")
    assert res["status"] == "success"
    assert res["title"] == "12345/2026"
    assert res["published_timestamp"] is not None

def test_malformed_html_graceful_failure():
    ext = RBIExtractor("rbi.org.in")
    # Missing title entirely
    html = "<html><body>Just some random text without a valid header</body></html>"
    res = ext.safe_extract(html, "https://rbi.org.in/test2")
    assert res["status"] == "partial_failure"
    assert res["title"] is None
    # Ensure it returns gracefully without crashing

def test_duplicate_document_hashing():
    ext = RBIExtractor("rbi.org.in")
    html = "<html><body>Title: A document. Date: 2026-01-01</body></html>"
    res1 = ext.safe_extract(html, "https://rbi.org.in/1")
    res2 = ext.safe_extract(html, "https://rbi.org.in/2") # different URL, same content
    assert res1["document_hash"] == res2["document_hash"]

def test_timestamp_fallback_behavior():
    ext = NSEExtractor("nseindia.com")
    # Date is unparseable junk
    html = "<html><body>Subject: Test Title. Date: Invalid-Date-String</body></html>"
    res = ext.safe_extract(html, "https://nseindia.com/test3")
    assert res["status"] == "success"
    assert res["title"] == "Test Title"
    assert res["published_timestamp"] is None # Fell back gracefully to None
