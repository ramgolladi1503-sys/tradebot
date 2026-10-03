# Hermes Stage 1 — Issue 9 missing-volume authority

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Preserve unavailable volume as unknown through trusted candle persistence
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Reproduced defect

A bounded offline call to `core.market_data._ingest_trusted_ltp_tick` with valid trusted LTP/time and `volume=None` is accepted by `core.ohlc_buffer.OhlcBuffer.update_tick`. The resulting bar records `volume=0` and has no explicit volume-quality provenance. `MarketSessionStore` treats that zero as observed data, although the input was absent. The store already supports a `None` volume and preserves it across restart when the bar provenance declares `volume_observation_complete=False`.

## Contract

1. At the trusted LTP ingestion boundary, volume is complete only when an explicit, convertible, finite, nonnegative volume accompanies the observation. Missing, malformed, non-finite, or negative volume must be passed as unknown (`None`) through the bar and durable store; it must never be encoded as zero.
2. Explicit zero remains an observed numeric value when a source actually supplies it. Invalid or absent fields cannot be converted to zero. An invalid volume does not discard an otherwise valid LTP observation.
3. Existing LTP source/time validation, OHLC event-time semantics, completion cutoff, bar identity, persistence idempotence, and same-session restore remain unchanged.
4. Do not alter generic/manual `OhlcBuffer` behavior, historical seed behavior, volume-delta policies, strategy inputs/thresholds, ranking, feed/risk/execution gates, or live/order/broker authority.
5. A consumer that requires volume must fail closed on unknown volume. The authorized patch does not add volume-dependent consumers or defaults.

## Scope

**requested_paths / allowed_paths:**
- `core/market_data.py` — annotate source volume completeness at `_ingest_trusted_ltp_tick`.
- `tests/core/test_market_session_runtime_bridge.py` — focused trusted-ingestion and restart assertion.
- `tests/test_market_data_warm_seed.py` — update the assertion that still expects absent live volume to be serialized as zero.
- `artifacts/issues_7_11/` — execution and verification record.
- `docs/agent_reviews/issues_7_11_hermes_issue9_volume_authority.md` — this contract.

**forbidden_paths:** `core/ohlc_buffer.py`, strategy/evaluator/ranking modules, feed health/recovery gates, risk/order/broker code, credentials, runtime launchers, token-universe configuration, and unrelated files.

## Expected tests

- Missing volume enters a trusted event-time bar as unknown, finalizes, persists, and remains unknown after a fresh `MarketSessionStore` instance reads it.
- An explicitly supplied zero or positive volume value is preserved without being marked unknown.
- Malformed, non-finite, and negative volume do not reject the valid price tick and persist as unknown.
- Existing `test_store_preserves_unknown_volume_through_restart` and Issue 9 store/runtime bridge suites remain green.

## Acceptance proof

The test must fail against the current implementation because its bar volume is zero despite `volume=None`. After the smallest ingestion-boundary repair, the persisted row must contain `volume is None`, carry `volume_observation_complete is False`, retain valid live source/time provenance, and pass integrity verification after reopen. Explicit zero must remain `0.0` with completeness true; malformed, non-finite, and negative volumes must remain unknown while valid LTP still enters the OHLC bar. `git diff --check` must pass and the diff must not touch forbidden paths.

**Hermes verdict:** scoped data-quality repair authorized. No runtime authority or strategy behavior is widened. Downstream consumers may see `null` where they previously saw a fabricated zero; tests and consumer inspection must confirm fail-closed handling.
