# V37 external finalization reserve

Finalization writes are bounded by the 1 MiB atomic-artifact cap, the bounded
JSONL rotation policy, and the 65,536-byte SQLite WAL policy. Optional Parquet
export is skipped under pressure. Finalization is fail-closed if the external
authority is unavailable.
