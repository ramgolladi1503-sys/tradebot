# Market Event Graph Live Constituent Source V1

mode: PAPER
candidate_id: market-event-graph-live-constituent-source-v1
decision: REVIEW_ONLY
reason: build causal completed NIFTY constituent-return rows for the merged advisory market-event graph
timestamp: 2026-07-30T09:28:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/market_event_graph_live_constituent_source_v1.md

## Agent Work Contract

```text
source_agent: ChatGPT GitHub agent
operation: IMPLEMENT_LIVE_CONSTITUENT_SOURCE
base_commit: 17262b4b6a42eb09d4d508bfdf6fe0d649ee32af
branch: integration/market-event-graph-live-constituent-source-v1
scope:
  - freeze a versioned current NIFTY 50 constituent reference manifest
  - provide an explicit official-CSV manifest refresh command with raw-source SHA-256
  - resolve exactly one NSE equity token per constituent and one NIFTY index token
  - request read-only WebSocket subscriptions only when explicitly enabled
  - reconstruct strict completed one-minute index and constituent returns from the canonical tick database
  - stop at the first missing interval rather than collapsing time
  - attach frozen producer metadata and durable caller-owned graph state
  - persist the graph idempotency watermark after advisory candidate construction
allowed_paths:
  - config/market_event_graph_nifty50_constituents_20260605.json
  - core/market_event_graph_tick_reader.py
  - core/market_event_graph_constituent_source.py
  - core/candidate_pool_orchestrator.py
  - scripts/refresh_market_event_graph_nifty50_manifest.py
  - tests/test_market_event_graph_constituent_source.py
  - tests/test_market_event_graph_manifest_refresh.py
  - docs/agent_reviews/market_event_graph_live_constituent_source_v1.md
forbidden_paths:
  - core/execution/**
  - core/risk/**
  - core/broker*
  - strategies/**
  - dashboard/**
  - live order configuration
acceptance:
  - exactly 50 unique manifest symbols
  - official CSV refresh records the raw-source digest and rejects duplicate/non-EQ membership
  - exact token resolution or fail closed
  - right-closed completed-minute tick semantics
  - minimum 40 same-minute constituent return pairs
  - no forward-fill and no skipped-minute graph compression
  - durable idempotency across a newly constructed context
  - no order, broker, risk, threshold, graph, ranking, or dashboard authority
```

## Scope Guard

In scope:

- Stage A live-input construction for the already frozen BUY_CALL graph.
- A read-only SQLite reader opened with `mode=ro`.
- Explicit source, token-resolution, subscription, coverage, and interval-gap evidence.
- An opt-in environment/metadata switch named `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE`.
- Session-scoped, atomic persistence of completed bars and the caller-owned graph watermark.
- A manually invoked refresh command for the current official constituent CSV.

Out of scope:

- No strategy retuning.
- No change to the graph, thresholds, next-bar delay, cooldown, or historical ledgers.
- No automatic runtime internet download.
- No option-contract mapping or premium-return analysis.
- No paper approval or live execution eligibility.
- No ranking or UI redesign.
- No bearish mirror activation.

Boundary verification:

- [x] no execution code changed
- [x] no risk code changed
- [x] no broker-order wrapper changed
- [x] no strategy file changed
- [x] source is disabled unless explicitly enabled
- [x] source output is advisory-only
- [x] manifest refresh is an explicit operator action, not a runtime network dependency

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk surfaces:

- `core/candidate_pool_orchestrator.py` is a runtime candidate collection path.
- `core.market_event_graph_constituent_source` may request market-data subscriptions.
- the checked-in constituent manifest affects breadth composition.

Controls:

- subscription uses the existing guarded `ensure_subscribed_tokens` API;
- subscription contains no order or portfolio operation;
- only NIFTY and only an explicit enable flag activate the source;
- the canonical NIFTY token is resolved through the existing market-data resolver;
- caller-supplied replay/test bars remain authoritative and are never replaced;
- the tick database is opened in read-only mode and never migrated;
- each one-minute row needs both current and prior close observations;
- the first missing index or constituent-coverage interval stops later construction;
- at least 40 constituent pairs are required;
- the manifest is a current reference snapshot, not historical membership evidence;
- the refresh command requires exactly 50 unique EQ symbols and records source bytes by SHA-256;
- the resulting candidate remains `SHADOW_ADVISORY_ONLY`.

## Grill Me Review

Verdict: PASS

Questions challenged:

- Can a missing minute be silently skipped? No. The source records `INTERVAL_GAP_BLOCKED` and stops before later rows.
- Can stale prices be forward-filled? No. A tick must exist inside each right-closed one-minute window.
- Can an ambiguous NSE symbol be selected? No. Every constituent must resolve to exactly one EQ token.
- Can the source run accidentally for BANKNIFTY or SENSEX? No. Non-NIFTY symbols return `NOT_APPLICABLE`.
- Can a restart replay the same graph? The caller-owned watermark is atomically persisted after candidate generation and reloaded by session.
- Can a malformed constituent CSV silently replace the manifest? No. The refresh command requires exactly 50 unique EQ symbols.
- Can this source place an order? No order API is imported or called.

## Hermes Review

Verdict: PASS

Architecture:

```text
official current constituent CSV --manual refresh--> versioned NIFTY manifest
-> cached NSE token resolution
-> guarded read-only WS subscription request
-> canonical tick SQLite read-only query
-> strict completed one-minute return rows
-> frozen breadth producer metadata
-> candidate-pool observer and advisory strategy
-> atomic session state persistence
```

The source, producer, observer, and strategy remain separate. The source does not
reimplement threshold classification or graph detection.

## GSD Review

Verdict: PASS

The delivery is a bounded vertical slice. It avoids modifying the large market-data
or execution orchestrators and attaches at the existing candidate-pool boundary.
The design is deterministic under injected instruments, ticks, time, state path,
and manifest CSV bytes.

## QA / Safety Review

Required tests cover:

- exactly 50 unique manifest constituents;
- official CSV digest and atomic refresh output;
- duplicate and non-EQ manifest rejection;
- successful and failed token resolution;
- right-closed minute boundaries including exact-second ticks;
- no forward-fill for a missing token/minute;
- complete five-minute source fixture containing the frozen A/B/C and entry bar;
- first-gap termination;
- atomic state-file creation;
- advisory candidate creation;
- persisted triplet identity preventing a second emission in a new context.

Safety assertions include:

```text
allowed_for_live_execution = false
is_order_action = false
broker_api_called = false
```

## Acceptance Proof

Run:

```bash
pytest -q \
  tests/test_market_event_graph_constituent_source.py \
  tests/test_market_event_graph_manifest_refresh.py \
  tests/test_market_event_graph_runtime_observer.py \
  tests/test_market_event_graph_breadth_producer.py \
  tests/test_market_event_graph_live_adapter.py \
  tests/test_market_event_graph_reversal.py \
  tests/test_candidate_pool_orchestrator.py

python -m py_compile \
  core/market_event_graph_tick_reader.py \
  core/market_event_graph_constituent_source.py \
  core/candidate_pool_orchestrator.py \
  scripts/refresh_market_event_graph_nifty50_manifest.py \
  tests/test_market_event_graph_constituent_source.py \
  tests/test_market_event_graph_manifest_refresh.py

python scripts/validate_agent_review_evidence.py
git diff --check
```

Acceptance requires behavioural assertions and exact reason codes, not shape-only or
non-null checks.

## Runtime Proof Required After Merge

Before Stage A can pass, run a complete live session with:

```text
MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE=true
```

Collect and reconcile:

- expected versus constructed completed minutes;
- resolved and subscribed token counts;
- per-minute participation;
- index-pair and constituent-pair misses;
- source lag and first-gap reason;
- producer and adapter acceptance;
- partial sequence progression;
- complete graph identity and duplicate suppression;
- state restoration after a controlled restart.

Before each membership-effective period, run the refresh command against the official
CSV and review the generated diff. The checked-in manifest is not valid for historical
backfill.

## What This PR Does Not Prove

This PR does not prove:

- today’s live WebSocket is healthy;
- all 51 requested tokens will remain subscribed or fresh;
- the graph will trigger during the observation session;
- the long-CE translation is profitable after spread, slippage, and fees;
- the frozen discovery is independently certified against a new untouched period;
- paper/manual approval or limited live trading is permitted;
- the bearish mirror works;
- ranking and UI concerns are resolved.

Truthful status after merge remains:

```text
LIVE_CONSTITUENT_SOURCE_IMPLEMENTED
STAGE_A_RUNTIME_AVAILABILITY_REQUIRES_LIVE_PROOF
NOT_OPTION_PREMIUM_VALIDATED
SHADOW_ADVISORY_ONLY
```

## Human Approval

Human approval is required before merge.

Approval should verify that explicit opt-in remains required and that this change is
limited to read-only market-data construction and advisory observation.
