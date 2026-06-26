import time
import tracemalloc
import sys
import os

# Assume running from repo root
sys.path.insert(0, os.path.abspath('.'))

from core.intelligence.fetchers.http_fetcher import HTTPFetcher
from core.intelligence.extractors.rbi_extractor import RBIExtractor
from core.intelligence.storage.sqlite_store import MIPSQLiteStore

def run_audit():
    results = {}
    
    # 1. Startup Latency
    start_time = time.perf_counter()
    import tempfile
    db_fd, db_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(db_fd)
    store = MIPSQLiteStore(db_path=db_path)
    fetcher = HTTPFetcher(source_id="TEST")
    extractor = RBIExtractor(source_domain="test.com")
    results["startup_latency_ms"] = (time.perf_counter() - start_time) * 1000

    # 2. Memory / Fetch Latency
    tracemalloc.start()
    fetch_start = time.perf_counter()
    # We use a reliable small mock URL or a real tiny endpoint if network is allowed.
    # For measurement truth, we'll fetch a known light endpoint: httpbin or example.com
    try:
        payload, status, lat = fetcher.fetch("https://example.com")
        results["fetch_latency_ms"] = (time.perf_counter() - fetch_start) * 1000
        results["fetch_status"] = status
    except Exception as e:
        results["fetch_status"] = str(e)
        results["fetch_latency_ms"] = -1
        payload = {"raw_content": ""}

    current_mem, peak_mem = tracemalloc.get_traced_memory()
    results["peak_memory_mb"] = peak_mem / (1024 * 1024)
    tracemalloc.stop()

    # 3. Parser Latency
    if payload and "raw_content" in payload:
        parse_start = time.perf_counter()
        # Mock HTML to force a parsing pass
        html = "<html><body>title: Mock Notification. date: 2026-01-01</body></html>"
        extracted = extractor.safe_extract(html, "https://example.com")
        results["parser_latency_ms"] = (time.perf_counter() - parse_start) * 1000
        results["parser_status"] = extracted["status"]
    
    # 4. Storage Latency
    storage_start = time.perf_counter()
    with store._get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO intelligence_sources (source_id, url) VALUES (?, ?)", ("TEST", "https://example.com"))
    _ = store.insert_fetch_run("TEST", "https://example.com", time.time(), "success", 0.1)
    results["storage_latency_ms"] = (time.perf_counter() - storage_start) * 1000

    # 5. Circuit Breaker Behavior
    cb_start = time.perf_counter()
    cb_fetcher = HTTPFetcher(source_id="CB_TEST")
    fail_count = 0
    for _ in range(6):
        _, stat, _ = cb_fetcher.fetch("http://invalid.domain.that.does.not.exist")
        if "CircuitBreakerOpen" in stat:
            break
        fail_count += 1
    results["circuit_breaker_trip_time_ms"] = (time.perf_counter() - cb_start) * 1000
    results["circuit_breaker_tripped_after_n_failures"] = fail_count

    # Print markdown report
    print("# Phase 15: Operational Audit Report\n")
    print("## Latency Measurements")
    print(f"- **Startup Latency**: {results.get('startup_latency_ms', 0):.2f} ms")
    print(f"- **Fetch Latency (example.com)**: {results.get('fetch_latency_ms', 0):.2f} ms")
    print(f"- **Parser Latency (HTML Normalization & Extractor)**: {results.get('parser_latency_ms', 0):.2f} ms")
    print(f"- **Storage Latency (SQLite Insert)**: {results.get('storage_latency_ms', 0):.2f} ms")
    print(f"- **Circuit Breaker Trip Latency (5 network failures)**: {results.get('circuit_breaker_trip_time_ms', 0):.2f} ms")
    
    print("\n## Resource Measurements")
    print(f"- **Peak Memory Usage (During Fetch)**: {results.get('peak_memory_mb', 0):.4f} MB")
    
    print("\n## Resilience Measurements")
    print(f"- **Circuit Breaker Tripped After**: {results.get('circuit_breaker_tripped_after_n_failures')} failures")
    print(f"- **Extraction Status**: {results.get('parser_status')}")

if __name__ == "__main__":
    run_audit()
