# Phase 6: Factor Model Hardening Report

## Enhancements Implemented
The initial string-based factor model has been replaced with a strictly enforced enum and whitelist approach (`core/intelligence/calibration/factors.py`). This guarantees that no strategy layer or extractor can invent unexplained heuristic scores.

1. **Allowed Factors Only**: The `Factor` initialization asserts that `self.name` exists within the `ALLOWED_FACTOR_NAMES` set. Allowed factors include `source_authority`, `freshness_delta_seconds`, `extraction_completeness`, `explicit_entity_mentions`, `entity_resolver_confidence`, `duplicate_status`, `document_category`, `source_health`, `historical_replay_impact`, `market_session_context`, and `replay_sample_size`.
2. **Explicit Factor Origin**: Each factor must declare its origin using the `FactorOrigin` enum (`MEASURED`, `CONFIGURED`, `INFERRED`, `CALIBRATED`).
3. **Stale Status Invalidations**: The `Factor.__post_init__` block was expanded to catch `stale_status=True`. If an event is marked stale, it aggressively overrides `execution_influence_allowed = False` even if the factor was previously calibrated.
4. **No Aggregate Arbitrary Scores**: The system explicitly does not sum up "confidence points". Any aggregate downstream must be an explicit mathematical function of these strictly typed bounds, and if one is missing, the downstream calculation (like Replay) drops to `INSUFFICIENT_EVIDENCE`.
