# 100k descriptor control audit

This note records the four-control 100,000-row offline replay comparison on
`ram/feed-fd-diagnosis-main-sync`.

Worktree:

- `/Users/madhuram/tradebot-feed-fd-diagnosis-main-sync`

Current HEAD:

- `f6fce400d2293102017468248aede00e5320051f`

Input envelope:

- parquet input: `/Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet`
- input SHA-256: `62410f680b0621c836e3b18e8a509126e3dfbcf40c61e3cc23d5c2bc30b95139`
- total input rows: `2,778,666`
- selected replay rows: `100,000`
- distinct instrument tokens in first 100k: `129`
- missing timestamps: `0`
- malformed timestamps: `0`

Corrected first-100k timestamp range:

- raw minimum `ts`: `1783569405.7407`
- raw maximum `ts`: `1783569979.745924`
- UTC minimum (`unit="s"`, UTC): `2026-07-09 03:56:45.740700006+00:00`
- UTC maximum (`unit="s"`, UTC): `2026-07-09 04:06:19.745923996+00:00`

The lower bound matches the known reference conversion:

- `1783569405.7407` -> `2026-07-09 03:56:45.740700+00:00`

The converted range is plausible for the July 9, 2026 capture window.

Executed controls:

1. sync untraced
2. async untraced
3. sync traced
4. async traced

Runner verdict in every run:

- `CONDITIONALLY_STABLE`
- `hard_failures = []`

Audit gate verdict:

- `100K_SYNC_ASYNC_PASS_BOUNDED_BURST`

Runner-level semantics and gate-level semantics are different layers:

- `CONDITIONALLY_STABLE` is the replay runner’s internal verdict.
- `100K_SYNC_ASYNC_PASS_BOUNDED_BURST` is the audit gate verdict for the
  four-control comparison.

Correctness results:

- requested rows: `100,000`
- processed rows: `100,000`
- timestamp fidelity: pass
- unexpected timestamp fallback count: `0`
- first semantic difference: `null`
- reconciliation assertions:
  - `decoded = normalized + rejected`: pass
  - `normalized = published + explicitly_dropped`: pass
  - `published = persisted + pending_at_shutdown`: pass
- unexplained message differences:
  - decoded: `0`
  - normalized: `0`
  - published: `0`

Deterministic hashes, identical across all four runs:

- `input_source_order_sha256`: `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985`
- `callback_order_sha256`: `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985`
- `normalization_order_sha256`: `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985`
- `persistence_order_sha256`: `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985`
- `canonical_semantic_output_sha256`: `9eefbd54d8a88201c4398b9d43b2e8c07f01c77947c7bed5ceb3a6aff8d7cf9d`
- `final_per_token_state_sha256`: `f103a7d35c540fd19ce74f422cd409f4305c0042acfcf038927fff4bd931b5b5`

Per-control evidence:

| Control | Exit code | Requested rows | Processed rows | Hard failures | Replay duration sec | Timestamp fidelity | Unexpected fallback | Reconciliation deltas | First semantic diff | Input hash | Callback hash | Normalization hash | Persistence hash | Canonical semantic hash | Final state hash | FD baseline | FD high-water | FD final | Explicit feed-side EMFILE | Worker start count | Worker thread name | Worker join completed | Worker terminated | Worker failures | Rows enqueued | Rows dequeued | Committed rows | Committed batches | Queue high-water | Queue depth at shutdown | Pending writes at shutdown |
| --- | ---: | ---: | ---: | --- | ---: | --- | ---: | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sync untraced | `0` | `100,000` | `100,000` | `[]` | `79.39792087500246` | pass | `0` | `0 / 0 / 0` | `null` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9eefbd54d8a88201c4398b9d43b2e8c07f01c77947c7bed5ceb3a6aff8d7cf9d` | `f103a7d35c540fd19ce74f422cd409f4305c0042acfcf038927fff4bd931b5b5` | `112` | `N/A` | `112` | `false` | `0` | `N/A` | `N/A` | `N/A` | `0` | `0` | `0` | `100,000` | `100,000` | `0` | `0` | `0` |
| async untraced | `0` | `100,000` | `100,000` | `[]` | `65.53204416600056` | pass | `0` | `0 / 0 / 0` | `null` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9eefbd54d8a88201c4398b9d43b2e8c07f01c77947c7bed5ceb3a6aff8d7cf9d` | `f103a7d35c540fd19ce74f422cd409f4305c0042acfcf038927fff4bd931b5b5` | `100` | `N/A` | `100` | `false` | `1` | `tick-store-flush` | `true` | `true` | `0` | `100,000` | `100,000` | `100,000` | `100,000` | `1` | `0` | `0` |
| sync traced | `0` | `100,000` | `100,000` | `[]` | `239.97992199999862` | pass | `0` | `0 / 0 / 0` | `null` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9eefbd54d8a88201c4398b9d43b2e8c07f01c77947c7bed5ceb3a6aff8d7cf9d` | `f103a7d35c540fd19ce74f422cd409f4305c0042acfcf038927fff4bd931b5b5` | `8` | `91` | `8` | `false` | `0` | `N/A` | `N/A` | `N/A` | `0` | `100,000` | `0` | `0` | `0` | `0` | `0` |
| async traced | `0` | `100,000` | `100,000` | `[]` | `480.0645647919955` | pass | `0` | `0 / 0 / 0` | `null` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9df4ef73f72a40a1bfd0f91672417739a3c7306ded34378b8b6e8cb8686a9985` | `9eefbd54d8a88201c4398b9d43b2e8c07f01c77947c7bed5ceb3a6aff8d7cf9d` | `f103a7d35c540fd19ce74f422cd409f4305c0042acfcf038927fff4bd931b5b5` | `48` | `91` | `48` | `false` | `1` | `tick-store-flush` | `true` | `true` | `0` | `100,000` | `100,000` | `100,000` | `100,000` | `1` | `0` | `0` |

Trace artifact verification:

| Control | Trace path | SHA-256 | Trace-event count | Callback-exit count | Baseline FD | High-water FD | Post-replay-shutdown FD | Post-worker-shutdown FD | Final FD |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sync traced | `.runtime/feed_robustness_audit/sync-100k-normal-traced/fd_trace.jsonl` | `642617744425b2d24a6c90b22ed867d06e2f2265c570c2ea93d0ec748bea733e` | `400,580` | `1,000` | `8` | `91` | `8` | `8` | `8` |
| async traced | `.runtime/feed_robustness_audit/async-100k-normal-traced/fd_trace.jsonl` | `6768f0dc6f60e7d8465ca11e7f27105a41cdc535c41cf185ff1aa465b6af0517` | `400,243` | `1,000` | `48` | `91` | `48` | `48` | `48` |

Why the callback-exit count is about 1,000:

- the trace file records multiple stages per row, not just callback exit;
- `callback_exit` is one stage in the per-row trace sequence;
- the `fd_trace.jsonl` files contain roughly 400k events for 100k rows, which is consistent with several trace points per row plus worker/shutdown instrumentation;

Performance observation:

- async untraced replay duration: `65.53204416600056 s`
- sync untraced replay duration: `79.39792087500246 s`
- async/sync duration ratio: `0.825`

This is not a correctness-gate failure.

It does not demonstrate an async throughput advantage.

The measured gap may reflect per-row commits, queue/thread overhead, or the absence of persistence pressure.

No causal explanation is proven by this run alone.

Queue-pressure limitation:

- async untraced queue-depth high-water: `1`
- async traced queue-depth high-water: `1`
- committed batches: `100,000` in both async runs

The async worker lifecycle and complete drain are proven, but meaningful producer-consumer backlog and slow-persistence pressure remain untested.

For the sync runs, `committed_batches = 100,000` and `flush_count = 0` because the runner records one commit per row in synchronous mode; there is no worker batch metric to compare to the async flush path, so that field is not a queue-pressure signal in sync mode. The traced sync control reports the same total commit count as the untraced sync control.

FD recovery:

- sync traced: baseline FD `8` -> high-water `91` -> final FD `8`
- async traced: baseline FD `48` -> high-water `91` -> final FD `48`

No explicit feed-side `EMFILE` occurred in any of the four controls.

Artifact directories:

- `.runtime/feed_robustness_audit/sync-100k-normal-baseline`
- `.runtime/feed_robustness_audit/async-100k-normal-baseline`
- `.runtime/feed_robustness_audit/sync-100k-normal-traced`
- `.runtime/feed_robustness_audit/async-100k-normal-traced`

Artifact SHA-256 values:

- sync baseline `run_manifest.json`: `dce59ec06f0f5f8885cd699f813dcbc24b3f23219b4802345c317f8310600bc9`
- sync baseline `checksums.json`: `2425008e6eb34048ddaa2cae8da0519b9e3defc5abefccea86d5dd33f10a7b97`
- sync baseline `feed_verdict.json`: `b6eac8c00f7211946c6824e8fd40d277c058ced04daf2fcc8ea5cec37c52c7ad`
- sync baseline `latency_report.json`: `c299fdfb2e92193b4c2b02a5d008794cd78c7c9f9db16a9f529f1c13eb1803b1`
- sync baseline `resource_snapshot.json`: `e35ca6906c6d8439a12b8f00bb248e2e47ffcc9a7e348ce89889bee2272a136c`
- sync baseline `timestamp_fidelity.json`: `c8971b794ddf0aa07fd57e157428bf95023ceae961033471db1890b3973847a6`
- async baseline `run_manifest.json`: `fe823fdb078f935569c5b9869823cefb7f49998a9832cf2ffc0efaf961fba42d`
- async baseline `checksums.json`: `25e264a6ca3f6c5619a6e0b16dfe10721d066344a68ae87e4f7c887980cf6574`
- async baseline `feed_verdict.json`: `b6eac8c00f7211946c6824e8fd40d277c058ced04daf2fcc8ea5cec37c52c7ad`
- async baseline `latency_report.json`: `57c1b1372f4f2c4cedf903db162aad92da6fd4ec68f7befece448053d71a1e59`
- async baseline `resource_snapshot.json`: `13b4df7a3a280724ed9b31b1be38e21319f9e8c06bd6080dfa1110ee2c0d6c46`
- async baseline `timestamp_fidelity.json`: `c8971b794ddf0aa07fd57e157428bf95023ceae961033471db1890b3973847a6`
- sync traced `run_manifest.json`: `2f40c5a01b35f156cf61f2a4df5126c6b06dc7a99180006ee512e6f73340e3d7`
- sync traced `checksums.json`: `093392873c90e4e200c8d8b36b476bd12f5668b5575aad00247bef1456a12b6d`
- sync traced `feed_verdict.json`: `b6eac8c00f7211946c6824e8fd40d277c058ced04daf2fcc8ea5cec37c52c7ad`
- sync traced `latency_report.json`: `54d1991db4a286bdea0ba72ba0e0bb7bcf453e13b8c5ec8316f0edf1e74f8196`
- sync traced `resource_snapshot.json`: `8953538267285435d3a821fc97993fda65941fa388a8e6436ad519477ddc395d`
- sync traced `timestamp_fidelity.json`: `c8971b794ddf0aa07fd57e157428bf95023ceae961033471db1890b3973847a6`
- async traced `run_manifest.json`: `4db87c1261edfb2ed643a211abe1f23c9642255a5ebf0ef7b0c003539fd20a0c`
- async traced `checksums.json`: `ec9057d5e7235dbb9a6cfe10455d6effe862a095ab10e67e7e680803d9a551be`
- async traced `feed_verdict.json`: `b6eac8c00f7211946c6824e8fd40d277c058ced04daf2fcc8ea5cec37c52c7ad`
- async traced `latency_report.json`: `7dc5375b88982c7811589934e919e75d45712f594c54bace11d9a0ab4028a454`
- async traced `resource_snapshot.json`: `16d92ae6debe1defca1bd6238a4b4f7038baf495e6378baea63d582ed27d110d`
- async traced `timestamp_fidelity.json`: `c8971b794ddf0aa07fd57e157428bf95023ceae961033471db1890b3973847a6`

Notes:

- The trace-event count is around 400k because the tracer records several
  stages per row; `callback_exit` is only one sampled stage.
- The async worker path is proven to start, drain, and terminate in the tested
  run, but the queue never built meaningful backlog.
- In sync mode, `worker_started`, `worker_join_completed`, and `worker_terminated` are not applicable because there is no worker lifecycle to observe.
- This gate does not prove any of the unsupported behaviors listed in the task.


## Agent Work Contract

N/A

## Scope Guard

N/A

## Grill Me Review

N/A

## Hermes Review

N/A

## GSD Review

N/A

## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
