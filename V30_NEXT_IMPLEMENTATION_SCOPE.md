# V30 next implementation scope

Before any low-disk threshold is promoted, implement and measure the missing
storage controls: SQLite WAL checkpoint/peak bound; operational JSONL rotation
and retention; Parquet temporary/output cap; explicit session-scoped artifact
rate bounds; and finalization reserve measurement across tick, depth, runtime,
CAS, funnel, risk, seal, and post-close writers. Re-run the complete write-path
inventory and independent storage-contract review afterward.

No live runtime, broker, order, risk, feed, or subscription behavior is part
of this scope.
