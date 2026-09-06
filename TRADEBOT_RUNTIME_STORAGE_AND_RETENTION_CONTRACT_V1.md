# TradeBot runtime storage and retention contract V1

Core records are admitted only after bounded serialization checks. Depth queue,
tick queue, tick batches, routed JSONL records, CAS atomic artifacts, and the
tick SQLite WAL use the maxima in `V37_PRIMITIVE_BOUND_REGISTER.csv`.
Optional Parquet and debug-only output may stop under pressure. Core evidence
must fail closed; no unbounded internal spill or silent fallback is allowed.
