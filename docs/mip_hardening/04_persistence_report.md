# Phase 4: Persistence Hardening Report

## Enhancements Implemented
The temporary local-file scaffolding (`core/intelligence/storage/store.py`) has been upgraded to a production SQLite backend (`core/intelligence/storage/sqlite_store.py`) matching the stability patterns of TradeBot's existing analytical and tick stores.

### Schema Design
1. **`intelligence_sources`**: Tracks the registry of configured sources, linking them to specific parser and extractor versions for data lineage.
2. **`intelligence_fetch_runs`**: Persists the outcome of every fetch attempt. Stores exact metrics including `fetch_timestamp`, `status`, `http_status`, `failure_reason` (typed by `FetchFailureReason` enum), `latency`, and `content_hash` for deduplication.
3. **`intelligence_documents`**: Stores deduplicated raw HTML/Text outputs linked by `content_hash` along with parsed metadata (`published_timestamp`, `title`).
4. **`intelligence_events`**: Represents the normalized intelligence context. Explicitly enforces an `advisory_only` boolean flag at the database level.
5. **`intelligence_factors`**: Granular tracking table where the aggregate event is broken down into specific factor values (e.g., `value=30.0`, `unit=seconds`, `name=freshness`).

## TradeBot Persistence Standards Match
- `PRAGMA journal_mode=WAL` and `synchronous=NORMAL` are enforced upon connection to prevent database locking during rapid fetch logging.
- `timeout=30.0` implemented to gracefully handle concurrent offline replay queries alongside live fetching loops.
