# Hermes Contract — Issue 11 persisted feed-truth ranking boundary

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Finding

The live cycle writes `feed_truth_latest.json` from `core.runtime_feed_truth_snapshot.build_feed_truth_snapshot`. That versioned artifact reports `source=runtime_feed_truth_snapshot_v1`, `feed_fresh`, `ws_connected`, and freshness summaries such as `latest_tick_age_sec`. The ranking path eventually passes the loaded mapping to `core.feed_hold_gate.apply_feed_hold_to_ranking`, whose classifier currently reads `feed_ok` and `last_tick_age_sec` but does not interpret the persisted artifact's `feed_fresh` field. A stale persisted snapshot can therefore be interpreted as healthy when websocket is connected and other recognized fields are absent.

Candidate-level fault isolation is a separate unresolved requirement. Score rows do not bind authoritative candidate dependencies to exact, fresh identity health, so this contract does not permit selective unholding.

## Contract

For payloads identified by `source=runtime_feed_truth_snapshot_v1`:

1. Runtime snapshot identity is established by the source family, the canonical writer marker, or the snapshot freshness/component signature; changing the source label cannot remove snapshot recognition. Unsupported or changed source labels fail closed. The supported v1 source requires `feed_fresh`, `ws_connected`, `market_closed_detected`, `underlying_tick_fresh`, and `option_tick_fresh` to be JSON booleans. Missing, null, string, or other values are unknown and fail closed.
2. `feed_fresh=false` is a global ranking hold with a stable reason indicating stale persisted feed truth.
3. `feed_fresh=true` is necessary but not sufficient: existing websocket, explicit global block, runtime/feed state, subscribed-option, and other canonical checks remain in force.
4. For v1, `feed_fresh=true` is internally consistent only when websocket is connected, the market is not closed, and both underlying and option freshness are true. Contradictory component fields fail closed. The classifier must not infer candidate-specific health from this aggregate snapshot, and must not reinterpret `stale_reason` as proof that a candidate is independent of the affected feed.
5. Legacy payloads with an explicit explicit top-level `feed_ok` decision, complete symbol-scoped health evidence, or finite, nonnegative numeric LTP age plus an explicitly supplied LTP SLA retain their behavior. An empty/opaque mapping, or transport connectivity without feed-health decision evidence, fails closed as missing health authority. Ranking callers that do not supply an LTP SLA cannot treat an age field alone as authority.
6. The ranking remains read-only. It emits no execution authority and does not call a broker or order API.

## Scope and safety

**Expected change surface:** canonical feed-health classification for this exact versioned producer contract and direct integration tests from producer output through ranking.

**Must not change:** feed production, artifact schema, feed freshness thresholds, candidate ranking semantics, strategy rules, symbol/token universe, candidate dependency declarations, recovery/auth latches, risk gates, broker adapters, order paths, paper/live authority.

**No new configuration keys.** The producer contract is versioned and already emits the fields required by this repair.

## Acceptance proof

- Actual healthy `build_feed_truth_snapshot` output reaches ranking without a hold when its freshness flag and required existing conditions are healthy.
- Actual stale output suppresses all ranks with a specific blocker.
- Missing, null, non-boolean, nonfinite, or negative age/freshness/component fields, unsupported or mutated source labels, stripped snapshot freshness with remaining snapshot markers, contradictory component fields, and empty/transport-only mappings fail closed.
- A contradictory snapshot (`feed_fresh=true`, websocket disconnected or global block true) still holds.
- Legacy canonical healthy and unhealthy mapping behavior remains unchanged.
- Direct, neighboring, and mutation attacks demonstrate the classifier cannot silently ignore or widen this versioned contract.
- Offline-only proof; no claim of live parity or candidate-level isolation.

## Rollback

Revert the source-specific classification branch and the integration test. This restores the known fail-open contract mismatch; it does not alter the producer schema or other safety gates.

## Freshness of the persisted snapshot itself

The producer's `feed_fresh=true` is evaluated at write time. A later consumer must not treat that decision as current indefinitely. The supported v1 snapshot therefore also requires a finite numeric, non-boolean `generated_epoch`, which must not be future-dated and must be no older than `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC`. The setting `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC` is added to the existing dedicated runtime-reliability config module with a 3-second default, aligned with the existing `FEED_RECOVERY_MAX_GAP_SEC`; deployments may override it explicitly. Missing/invalid configuration or timestamp fails closed. This check does not change per-tick LTP/option SLA thresholds.
