# PR955 Depth Queue Resilience Review

## Agent Work Contract
- source_agent: hermes -> gsd
- action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, PLAN_PR, GENERATE_TESTS, GENERATE_PATCH
- title: Bound and account for depth persistence backlog
- scope: depth persistence queue defaults/configuration and offline stress/accounting tests.
- requested_paths: config/config.py, core/depth_store.py, core/storage_bounds_v37.py, tests/test_depth_persistence_batching.py, tests/test_depth_store_accounting.py, tests/test_storage_bounds_v37.py, tests/test_c1_c2_regime_decoupling.py, docs/agent_reviews/.
- allowed_paths: listed files only.
- forbidden_paths: order, broker, strategy behavior, feed freshness, kill switches, credentials, live config, and unrelated files.
- expected_tests: depth batching, accounting, rate-limit, storage bound, and immutable-config audit tests; repository deterministic suite where practical.
- acceptance_proof: stalled writer yields bounded visible rejection; incident-sized burst drains with exact accounting; no false persistence; exact config hash pin remains active.

## Scope Guard
Depth snapshots remain bounded and asynchronous. Every accepted item must be persisted or explicitly rejected/accounted. Queue capacity is a burst buffer, not proof of sustainable throughput. Batch size is bounded. No feed freshness, order, or broker behavior changes. The declared storage-bound item count must match maximum configured queue size. Invalid capacities fail closed before the worker thread starts.

## Grill Me Review
- Failure mode: a small burst test passes while production backlog scale fails. Repaired coverage stalls the writer and exercises a 37,936-item synthetic backlog.
- Failure mode: queue saturation silently loses snapshots or claims them persisted. The overload test requires explicit rejection provenance and reconciled accounting.
- Remaining limitation: synthetic tests do not establish production soak throughput, peak RSS, or real raw-depth replay performance.

## Hermes Review
Contract: read_only=true; is_order_action=false; broker_api_called=false; allowed_for_live_execution=false. Queue capacity is finite; rejected work is observable; accepted = persisted + rejected + in-flight/queued remainder at each snapshot. The configured batch is capped by the code's positive batch setting. No silent fallback may claim persistence.

## GSD Review
Execution strengthens burst and stalled-consumer tests, retains explicit configuration keys, updates the exact immutable-config SHA baseline for the reviewed depth-persistence settings, and aligns the shared item-count bound with the configured maximum. The hash assertion remains exact and will fail on any later config edit.

## QA / Safety Review
- High-Risk Path Review: `config/config.py` contains runtime configuration. The change is limited to depth persistence queue capacity, enqueue timeout, and bounded batch size. It does not alter broker, order, risk, freshness, or live-mode gates. The existing immutability test's exact SHA was advanced to the reviewed complete file hash: `b1b23141428530b8e51f98f73810f5ecf77df49187d9d92538fb7cc71f8ba950`.
- High-Risk Path Review: `core/depth_store.py` rejects configured queue capacities outside the declared positive bound before starting persistence work.
- Tests run: depth batching, accounting, rate-limit, storage bounds, and exact config immutability audit (31 passed); `git diff --check` passed.
- Current-base full CI failure also reports frozen PR818 baseline drift across unrelated files. That gate requires repository-level resolution and is not waived here.

## Acceptance Proof
The 37,936-item synthetic burst blocks its first database write, queues the remaining workload, drains through SQLite in batches no larger than 250, and asserts persisted count equals enqueued count with zero rejection or unaccounted remainder. The stalled-writer case asserts queue bounds, visible rejection, and exact accounting. The derived serialized queue payload upper bound is 742 × 65,536 bytes; Python object overhead is additional. Configured capacity 0, negative, or greater than the declared maximum must raise before a worker thread starts.

## Runtime Proof Required After Merge
Use a read-only production observation or representative raw depth replay to measure producer/consumer rate, queue high-water mark, rejection count, batch latency, and memory under sustained load. Do not interpret the synthetic burst as runtime proof.

## What This PR Does Not Prove
It does not prove sustainable production throughput, memory headroom at the configured capacity, actual market-depth replay equivalence, absence of unrelated CI failures, or live readiness.

## Human Approval
Human approval is required for runtime configuration and merge. This change does not authorize broker API calls, order actions, or live mode.
