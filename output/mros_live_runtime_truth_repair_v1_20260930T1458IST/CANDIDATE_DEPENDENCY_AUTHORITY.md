# Candidate dependency authority and runtime enforcement

**Status: PARTIAL / BLOCKED.** A repository-native exact-ID registry now records only source-backed declarations and makes incomplete/unknown dependencies fail closed. No current candidate is certified execution-ready because identity-scoped freshness and complete authority are not available.

The implementation is in `core/candidate_feed_dependencies.py` and `core/symbol_execution_safety.py`. Registry entries are immutable dataclasses, keyed by exact `candidate_id`; each records coarse required domains separately from required identities, source SHA-256 digests, authority status, scope, and unresolved requirements. The safety consumer compares caller-supplied domains to registry authority, rejects unknown/missing IDs when structured domain health is present, and blocks advisory, historical, or partial entries. A payload cannot make an incomplete declaration executable by claiming healthy coarse domains.

## Source-backed registry entries

| Candidate ID | Authority | Recorded dependency evidence | Execution result |
|---|---|---|---|
| `CAS_MORNING_REVERSAL_SHORT_HORIZON_V1` | Verified advisory declaration | NIFTY `INDEX_SPOT`; canonical registry and advisory evaluator sources are digest-bound | Blocked for execution: advisory-only contract |
| `INTRADAY_OPENING_DRIVE_V1` | Partial frozen declaration | NIFTY spot, NIFTY futures, NIFTY options domains; exact futures/option identities remain unresolved | Blocked: no authoritative futures identity, dynamic option identity not joined to health, historical research halted |
| `S1_MOMENTUM_OVERNIGHT_V1` | Partial frozen declaration | NIFTY50 spot signal and T-1 heritage | Blocked: no identity-scoped spot health; T-1 authority is separate and blocked; historical-only |
| `S4_MONDAY_OVERNIGHT_V1` | Partial frozen declaration | NIFTY50 spot signal, Monday calendar, and T-1 heritage | Blocked for the same authority gaps; historical-only |
| `DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION` | Partial frozen shadow declaration | NIFTY futures signal, NIFTY spot 15:25 ATM mapping, dynamic NIFTY option observation; runner enforces local quote age | Blocked: active futures and option contract identities are not bound to health; canonical freshness policy and shadow-vs-execution authority remain unresolved |
| `DAY_TO_NIGHT_MOMENTUM_V1` | Partial runner inventory | Exact runner ID found; no versioned frozen dependency contract found | Blocked: inputs, identities, optional/fallback behavior, and freshness remain undeclared |
| `C1_INTRADAY_15M_IMPULSE`, emitted ID `ENTRY_C_INTRADAY_15M_IMPULSE_50BPS_X_STOP_40BPS_CLOSE`, alias `C1` | Partial governed evaluator declaration | Evaluator consumes NIFTY `MarketMemorySnapshot` features and candidate declares NIFTY Futures entry/exit; orchestrator fallback synthesizes the snapshot from generic `market_data` if the session store is absent | Blocked: feed identities are not bound to authoritative health; fallback provenance is not established; `freshness_watermark` is not an age SLA |
| `C2_OVERNIGHT_TREND`, emitted ID `ENTRY_E3_OVERNIGHT_TREND_1512_SIGNAL_1514_ENTRY_OPEN_EXIT`, alias `C2` | Partial governed evaluator declaration | Evaluator consumes NIFTY session-open/trend memory and candidate declares NIFTY Futures entry/exit; same generic-memory fallback applies | Blocked for the same identity, fallback provenance, and freshness reasons |
| `nifty_intraday`, `banknifty_intraday` | Partial `StrategyContract` labels | Raw labels `NIFTY_SPOT`/`NIFTY_OPTIONS` and `BANKNIFTY_SPOT`/`BANKNIFTY_OPTIONS` are retained as coarse source text; no enum mapping is invented | Blocked: domain mapping, identity, and freshness are undeclared |

## Unknown families and tests

The JSON companion lists candidate-producing registry and family-contract names with no source-backed dependency declaration, including all 12 movement generators, the two execution entries, MEG reversal, aggregate/deferred entries, C1/C2 and generic families, plus unverified day-to-night candidates. These IDs resolve to `UNKNOWN_BLOCKED`; a family name or instrument-family label is not authority.

Focused tests prove duplicate/malformed/stale source-digest rejection, domain mismatch rejection, unknown/missing ID blocking, and non-executable advisory/historical status. Existing feed-health tests prove healthy required index domains can remain `feed_ok` while unrelated stock degradation remains visible. Candidate execution is still blocked when no exact registry identity authority exists. There is no optional dependency proven in the registry, so optional-stale nonblocking behavior is not claimed. Runtime undeclared-access detection is also not implemented because candidate producer access contracts remain unavailable.

The legacy symbol-only compatibility path remains explicitly `LEGACY_UNRESOLVED` with `registry_coverage=false` only when there is no candidate ID and no structured domain-health payload; its existing selected-symbol freshness checks remain. It is not a live-readiness claim.

The registry now records 14 exact IDs, including day-to-night and C1/C2 aliases/emitted IDs, while 23 other family labels remain unknown or unverified. Exact ID coverage is not complete dependency authority: only declarations whose sources fully establish identity, freshness, optional/fallback, and breadth behavior could be marked verified. C1/C2's generic-memory fallback and non-age-bounded freshness watermark are specifically recorded as unresolved. Safety markers are `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`. No strategy threshold, broker path, or authorization state changed.
