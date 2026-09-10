# V31 storage authority decision

The V30 inventory remains incomplete under V31’s stricter fields. SQLite WAL
peak/checkpoint behavior, operational JSONL rotation/retention, Parquet output
retention, and complete finalization amplification do not have authoritative
bounds. The bounded probes are evidence for plausibility only and cannot be
promoted to a full-session reserve.

STORAGE_CONTRACT_FROZEN=false
LOW_DISK_CONTRACT_FROZEN=false
STORAGE_CONTROL_IMPLEMENTATION_REQUIRED=true
LOW_DISK_AUTHORITY_DERIVABLE=false

No V31 runtime storage control or successor source patch is authorized.
