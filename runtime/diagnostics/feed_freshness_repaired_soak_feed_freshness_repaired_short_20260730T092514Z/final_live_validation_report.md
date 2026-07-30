# Final Live Validation Report

Principal verdict: `LIVE_SOAK_FAILED_DOWNSTREAM_PIPELINE`

This was an operator-approved shortened validation, not the formal 60-minute soak. The 75-minute market-time gate was explicitly waived by the operator after it failed.

## Identity

- Branch: `fix/feed-freshness-recovery-v1`
- Commit: `5e184de8e574ca27452b3fafa8962da0d44f397b`
- Evidence directory: `/Users/madhuram/tradebot-feed-freshness-recovery-v1/runtime/diagnostics/feed_freshness_repaired_soak_feed_freshness_repaired_short_20260730T092514Z`
- Observation start: `2026-07-30T14:57:26.966687+05:30`
- Observation end: `2026-07-30T15:29:03.761120+05:30`
- Samples: `376` at five-second cadence
- Initial main PID: `42514`
- Manifest SHA-256 before final report reseal: `87e45e5c5684f9655afc3edfa6bf42439a6ada6c56fafb45329ba88e0993765f`

## Verdict Basis

Physical feed transport stayed alive and truthful: `transport_false_count=0`, no reconnect block appeared, and `process_restart_required` was never true. The old defective sequence `partial_activity -> partial_recovery -> permanent RECOVERY_BLOCKED -> false ws_connected=false` did not reappear.

The validation still fails downstream readiness because `execution_feed_ready` was true in `0/376` samples, `subscription_registry_consistent` was true in `0/376` samples, and truth integrity was `ALERT` in `371/376` samples. Candidate and ranking snapshots advanced, but emitted candidates stayed blocked/advisory/queue-only and no execution intent was allowed.

## Checkpoint Matrix

| checkpoint | timestamp_ist | process_alive | physical_transport_connected | critical_fresh_ratio | core_fresh_ratio | subscription_registry_consistent | canonical_feed_state | execution_feed_ready | feed_ok | reconnect_blocked_reason | process_restart_required | memory_rss | thread_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| T+00 | 2026-07-30T14:57:26.966687+05:30 | True | True | 1.0 | 0.9857142857142858 | False | DEGRADED_LOCAL | False |  |  | False | 267872 | 16 |
| T+05 | 2026-07-30T15:02:27.690061+05:30 | True | True | 1.0 | 0.9705882352941176 | False | DEGRADED_LOCAL | False |  |  | False | 217840 | 16 |
| T+10 | 2026-07-30T15:07:27.166116+05:30 | True | True | 1.0 | 0.9692307692307692 | False | LIVE | False | True |  | False | 192288 | 16 |
| T+15 | 2026-07-30T15:12:29.575259+05:30 | True | True | 1.0 | 0.96875 | False | DEGRADED_LOCAL | False | True |  | False | 345664 | 16 |
| T+20 | 2026-07-30T15:17:27.723725+05:30 | True | True | 1.0 | 0.96875 | False | DEGRADED_LOCAL | False | True |  | False | 247984 | 16 |
| T+25 | 2026-07-30T15:22:30.107747+05:30 | True | True | 1.0 | 0.96875 | False | DEGRADED_LOCAL | False | True |  | False | 422224 | 16 |
| T+30 | 2026-07-30T15:27:27.909016+05:30 | True | True | 1.0 | 0.9827586206896551 | False | DEGRADED_LOCAL | False | True |  | False | 224960 | 16 |

## Feed-State Transitions

- 2026-07-30T14:57:26.966687+05:30: None -> DEGRADED_LOCAL trigger=sampled_runtime_snapshot transport=True critical=1.0 core=0.9857142857142858 stable_cycles=12
- 2026-07-30T15:01:11.777664+05:30: DEGRADED_LOCAL -> LIVE trigger=sampled_runtime_snapshot transport=True critical=1.0 core=0.9705882352941176 stable_cycles=4
- 2026-07-30T15:01:16.827599+05:30: LIVE -> DEGRADED_LOCAL trigger=sampled_runtime_snapshot transport=True critical=1.0 core=0.9705882352941176 stable_cycles=6
- 2026-07-30T15:07:27.166116+05:30: DEGRADED_LOCAL -> LIVE trigger=sampled_runtime_snapshot transport=True critical=1.0 core=0.9692307692307692 stable_cycles=26
- 2026-07-30T15:07:32.222180+05:30: LIVE -> DEGRADED_LOCAL trigger=sampled_runtime_snapshot transport=True critical=1.0 core=0.96875 stable_cycles=27

## Metrics

- Partial degradation occurred: `yes`, sampled canonical state included `['DEGRADED_LOCAL', 'LIVE']`.
- Genuine recovery exercised: `no`; no real `LIVE -> DEGRADED_LOCAL -> VERIFYING_RECOVERY -> LIVE` sequence was observed.
- Maximum degraded duration: approximately `1285` seconds by five-second sampling.
- Availability as LIVE/bounded-local-degraded/verification states: `100.00%`.
- Critical freshness ratio: min `0.6666666666666666`, max `1.0`.
- Core freshness ratio: min `0.96875`, max `1.0`, avg `0.9741451540927579`.
- Feed OK samples: `349/376`.
- Execution-ready samples: `0/376`.
- Reconnect blocked reason: never present.
- Process restart required: `False`.
- Thread count min/max: `16/17`.
- RSS KB min/max/start/end: `52240/933888/267872/404720`.

## Downstream E2E

- Feed runtime snapshot: `ADVANCING`.
- Feed truth: `ADVANCING`, but integrity stayed `ALERT` in sampled runtime health.
- Orchestrator cycle: `ADVANCING` after startup, not stuck in original feed-fatal sleep.
- Candidate funnel: `ADVANCING`; candidate snapshot moved from `2026-07-30T14:57:25.130371+05:30` to `2026-07-30T15:29:02.206085+05:30`.
- Ranking snapshot: `ADVANCING`; ranking moved from `2026-07-30T14:57:25.124824+05:30` to `2026-07-30T15:29:02.202793+05:30`.
- Execution-intent gate: `FAIL_CLOSED`; sampled `execution_intent_count=0` and console evidence showed `execution_allowed=False` with queue-only/advisory/block final actions.

## Candidate-Local Safety

No stale candidate was observed as executable in the sampled execution gate. Console evidence showed candidates emitted as blocked/advisory/queue-only with `execution_allowed=False` and final emit aborts such as `ltp_not_live` or latency/feed truth blockers.

## Resource Health

Thread count stayed bounded at `16-17`. RSS fluctuated substantially and reached `933888` KB in the short run, then ended at `404720` KB. This is a resource-health concern requiring a longer controlled run or profiling before merge.

## Blockers

- `subscription_registry_consistent=false` for every sampled point.
- `execution_feed_ready=false` for every sampled point.
- `truth_integrity_status=ALERT` persisted in sampled runtime health.
- The run was shortened and cannot satisfy formal 60-minute soak acceptance.
- Real recovery transition was not exercised.

## Merge Recommendation

`REQUIRES_ADDITIONAL_RECOVERY_EVENT_VALIDATION`

Do not merge as fully live-validated. The patch appears to fix the old terminal partial-recovery latch under live observation, but downstream readiness remains blocked and real recovery was not naturally exercised.
