# V32 finalization reserve

FINALIZATION_RESERVE_MODEL=BLOCKED
FINALIZATION_RESERVE_MAX_BYTES=UNKNOWN

The required formula must include queued tick/depth bytes, WAL finalization,
runtime/CAS/risk/seal/post-close artifacts, and atomic temporary files. At least
the WAL and authoritative JSONL terms remain unknown, so no reserve is
invented.
