# Market Event Graph Live Breadth Runtime Observation V1

mode: PAPER
candidate_id: market-event-graph-live-breadth-runtime-v1
decision: REVIEW_ONLY
reason: expose causal live breadth availability, rejection, partial-sequence, producer, and adapter evidence without execution authority
timestamp: 2026-07-30T09:28:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/market_event_graph_live_breadth_runtime_v1.md

## Agent Work Contract

```text
source_agent: ChatGPT GitHub agent
operation: IMPLEMENT_STAGE_A_RUNTIME_AVAILABILITY
base_commit: cd14d1a4ace7dbfbdea98890280765e0e67d8b8e
branch: integration/market-event-graph-live-breadth-v1
scope:
  - observe whether completed_constituent_bars reach the market-event graph runtime
  - distinguish missing data, contract mismatch, malformed rows, low coverage, ordering defects, stale input, partial sequences, and complete graph acceptance
  - publish the observation inside the read-only candidate-pool report
allowed_paths:
  - core/market_event_graph_runtime_observer.py
  - core/candidate_pool_orchestrator.py
  - tests/test_market_event_graph_runtime_observer.py
  - docs/agent_reviews/market_event_graph_live_breadth_runtime_v1.md
forbidden_paths:
  - core/execution/**
  - core/risk/**
  - core/broker*
  - config/**
  - strategies/**
  - dashboard/**
acceptance:
  - missing live breadth input is explicitly visible
  - valid completed intervals are counted
  - causal event labels and partial graph progress are visible
  - producer and adapter status are visible
  - rejection counts preserve their exact reason classes
  - no broker call, order action, or live promotion is introduced
```

## Scope Guard

This change is limited to Stage A runtime availability and Stage B observability groundwork.
It does not subscribe to NIFTY constituents, fetch bars, change the frozen graph,
change thresholds, select an option contract, rank a candidate, or authorize any
execution path.

Protected boundaries:

- frozen strategy ID and provenance remain unchanged;
- `breadth_down_1:HIGH -> index_breadth_divergence:LOW -> breadth_down_1:LOW` remains unchanged;
- next-completed-bar entry delay remains unchanged;
- option-premium validation remains absent;
- the candidate pool remains read-only and non-ranking;
- all output explicitly carries no order or broker authority.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

`core/candidate_pool_orchestrator.py` is runtime-adjacent because it is the default
candidate collection path. The modification adds only a pure observation call and
copies its result into report metadata. It does not alter candidate generators,
no-trade logic, option confirmation, executable counts, ranking, capital selection,
or broker behavior.

Safety review:

- observer input is read-only;
- strategy runtime state is not advanced by the observer;
- malformed input produces reason-coded evidence rather than a candidate;
- observer output always sets `allowed_for_live_execution=false`;
- candidate-pool `read_only` and `is_order_action=false` contracts remain intact.

## Grill Me Review

Verdict: PASS

Questions challenged:

- Could a missing feed be mistaken for a quiet market? No; it reports `MISSING_SOURCE_BARS`.
- Could a contract mismatch be mistaken for no signal? No; it reports `CONTRACT_INVALID`.
- Could malformed timestamps be silently sorted? No; supplied-order defects are counted and rejected.
- Could partial graph progress emit an order? No; the observer has no candidate or order API.
- Could observation mutate the idempotency watermark? No; the producer and adapter calls used here are read-only.

## Hermes Review

Verdict: PASS

Architecture remains separated:

```text
completed constituent intervals
-> read-only runtime observer
-> producer acceptance evidence
-> adapter acceptance evidence
-> candidate-pool report metadata
```

The observer does not become another strategy implementation. It reports the same
frozen contract and delegates complete graph acceptance to the existing producer
and adapter.

## GSD Review

Verdict: PASS

Delivery is intentionally narrow and testable. It creates one observable vertical
slice for runtime availability before implementing persistence, option economics,
UI rendering, or paper reconciliation.

## QA / Safety Review

Covered behaviours:

- missing source metadata;
- exact complete graph accepted by producer and adapter;
- causal partial sequence before an entry bar exists;
- duplicate timestamp rejection;
- constituent coverage rejection;
- frozen provenance mismatch;
- propagation into the candidate-pool report;
- read-only and no-order assertions.

No test uses broker mocks or favourable market outcomes as proof.

## Acceptance Proof

Expected focused command:

```bash
pytest -q \
  tests/test_market_event_graph_runtime_observer.py \
  tests/test_market_event_graph_breadth_producer.py \
  tests/test_market_event_graph_live_adapter.py \
  tests/test_market_event_graph_reversal.py \
  tests/test_candidate_pool_orchestrator.py
```

Expected static checks:

```bash
python -m py_compile \
  core/market_event_graph_runtime_observer.py \
  core/candidate_pool_orchestrator.py \
  tests/test_market_event_graph_runtime_observer.py

git diff --check
python scripts/validate_agent_review_evidence.py
```

Acceptance requires exact status and reason preservation, not merely object shape or
non-null output.

## Runtime Proof Required After Merge

A live-session campaign must still demonstrate:

- `completed_constituent_bars` arrives on every expected completed interval;
- participation stays at or above the frozen minimum;
- source and context timestamps remain aligned;
- stale, malformed, incomplete, low-coverage, and contract-invalid counts remain explainable;
- partial sequences progress causally;
- a genuine complete graph reaches both producer and adapter exactly once;
- the observation metadata reaches the operational dashboard or journal.

The current PR provides the evidence contract needed to measure those facts; it does
not claim that a live feed already supplies them.

## What This PR Does Not Prove

This PR does not prove:

- live constituent subscriptions exist;
- breadth input arrives reliably during a trading session;
- the strategy will trigger at any particular frequency;
- actual CE contracts are profitable;
- option fills, slippage, fees, stop, target, or holding rules are valid;
- the graph is eligible for paper or live execution;
- PR #742 is vertically certified;
- the bearish mirror has an edge.

Truthful status remains:

```text
SHADOW_ADVISORY_ONLY
NOT_OPTION_PREMIUM_VALIDATED
STAGE_A_OBSERVABILITY_IMPLEMENTED_RUNTIME_AVAILABILITY_UNPROVEN
```

## Human Approval

Human approval is required before merge.

Approval should confirm that the PR remains an observability-only Stage A change and
that live feed subscription, historical option economics, paper eligibility, and
manual live trials remain separate gated campaigns.
