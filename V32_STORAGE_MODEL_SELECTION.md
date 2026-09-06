# V32 storage model selection

STORAGE_SAFETY_MODEL=BLOCKED

Model 1 (full-session prediction) is unsupported by the partial historical
session. Model 2 (reserve-first bounded failure) is not yet provable because
material core JSONL writers and SQLite WAL/checkpoint behavior lack complete
deterministic bounds. V32 therefore selects neither model for release.
