# Agent 4 Report: Fetch Infrastructure

## Infrastructure Components
The Fetch Infrastructure has been fully isolated under `core/intelligence/`. It is designed to act purely as a data-gathering pipeline that fails safely and respects external domain rules.

### Implemented Modules:
1. **Source Registry** (`sources.py`): Typed configurations mapping out RBI, SEBI, NSE sources, enforcing fetch frequency and category types.
2. **Robots Gate** (`robots_gate.py`): An extremely strict, dependency-free implementation of a `robots.txt` gate. It reads the target's rules, skips on disallow, and strictly sleeps based on the provided `Crawl-delay`. It fails closed on any parsing errors.
3. **Storage Interfaces** (`storage/store.py`): Contains `RawStore` (retains full HTML/Content hashing to trace back all evidence) and `EvidenceStore` (an append-only log storing JSONL structured evidence).
4. **Base Fetcher** (`fetchers/base.py`): Abstract component ensuring all child fetchers must pass the `robots_gate.can_fetch()` validation.
5. **Graceful HTTP Fetcher** (`fetchers/http_fetcher.py`): Fallback HTTP ingestion honoring the robots gate and timeouts.

## Degradation & Failsafes
The pipeline enforces:
- **No Anti-Bot Bypass**: We strictly use default user-agents and do not attempt to bypass CAPTCHAs unless the source explicitly permits headless browsing or we have a legitimate API integration.
- **Fail Closed**: If a domain blocks us, or `robots.txt` is missing/unreadable, the fetcher returns `None`. It does not retry uncontrollably.
- **Dependency Isolation**: Third-party integrations (like Firecrawl/Crawl4AI) will be wrapped in `try/except ImportError` so the system degrades smoothly if packages or API keys are missing.

This fetch layer operates purely to gather text and HTML. It evaluates no trading signals.
