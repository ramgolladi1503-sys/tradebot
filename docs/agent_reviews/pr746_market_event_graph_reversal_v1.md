# PR 746 — Frozen Market Event Graph Reversal V1

mode: PAPER
candidate_id: pr746-market-event-graph-reversal-v1
decision: REVIEW_ONLY
reason: reproduce the frozen underlying breadth-event graph exactly and expose it only as a fail-closed shadow advisory candidate
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr746_market_event_graph_reversal_v1.md

## Agent Work Contract

```text
source_agent: ChatGPT and Codex, with an independent audit branch
source_implementation_head: c65075f5922ccf37dde265419244df877ef104da
independent_audit_commit: 2e1913b5758b22e6f32ce27fb357d4d79a1e9735
action: REVIEW_AND_PUBLISH_SHADOW_ONLY
title: Faithfully reproduce frozen market-event graph timing
scope: recover the original evidence, freeze the exact thresholds and chronological split, implement strict consecutive-row graph timing with next-completed-bar emission, require immutable provenance and caller-owned idempotency state, and retain advisory-only authority
requested_paths:
  - core/market_event_graph_breadth_producer.py
  - core/market_event_graph_contract.py
  - core/market_event_graph_live_adapter.py
  - strategies/movement/market_event_graph_reversal.py
  - research/market_event_graph_reversal_v1/*
  - scripts/reproduce_market_event_graph_reversal_v1.py
  - tests/test_market_event_graph_breadth_producer.py
  - tests/test_market_event_graph_reversal.py
  - docs/agent_reviews/pr746_market_event_graph_reversal_v1.md
allowed_paths:
  - core/market_event_graph_breadth_producer.py
  - core/market_event_graph_contract.py
  - core/market_event_graph_live_adapter.py
  - strategies/movement/market_event_graph_reversal.py
  - research/market_event_graph_reversal_v1/*
  - scripts/reproduce_market_event_graph_reversal_v1.py
  - tests/test_market_event_graph_breadth_producer.py
  - tests/test_market_event_graph_reversal.py
  - docs/agent_reviews/pr746_market_event_graph_reversal_v1.md
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - python scripts/reproduce_market_event_graph_reversal_v1.py --archive /Users/madhuram/Downloads/causal-market-state-v1-evidence-v3.zip
  - pytest -q tests/test_market_event_graph_breadth_producer.py tests/test_market_event_graph_live_adapter.py tests/test_market_event_graph_reversal.py tests/test_movement_registry.py tests/test_strategy_registry.py tests/test_movement_contract.py
  - pytest -q tests/test_opening_movement_strategies.py tests/test_compression_trend_movement_strategies.py tests/test_vwap_trap_movement_strategies.py tests/test_event_late_day_movement_strategies.py tests/test_market_event_graph_breadth_producer.py tests/test_market_event_graph_live_adapter.py tests/test_market_event_graph_reversal.py tests/test_movement_registry.py tests/test_strategy_registry.py tests/test_movement_contract.py
  - python scripts/validate_agent_review_evidence.py
  - python scripts/run_unified_ce_gates.py
  - git diff --check
acceptance_proof:
  - original archive and dataset hashes match the frozen evidence
  - train-only thresholds match independently
  - train, validation, and holdout ledgers match independently
  - strict A(t-2) -> B(t-1) -> C(t) timing is enforced
  - no candidate is emitted until the next completed bar
  - duplicate timestamps, duplicate source-bar ends, session crossing, stale evidence, malformed provenance, and threshold overrides fail closed
  - repeated evaluation with persisted state cannot duplicate a candidate
  - candidate remains advisory-only and cannot authorize an order
```

Frozen evidence:

```text
source archive SHA-256: fde3f5c74f12bf59d80d39012bffd89a9411954b9207561f92b792ade31099b3
dataset SHA-256: 30f3d399404a299da6cb99b600a3f2b7346deb74653d5f4a8ebf8849ebefe73c
split manifest SHA-256: 016ba53e4bdba61ae558e024ece55ea2ab129e8262ff8e5f56c0b7db83ec2b6a
train occurrences: 168
validation trades: 115
validation profit factor: 2.4567905524018094
holdout trades: 25
holdout profit factor: 4.173855459438616
```

## Scope Guard

In scope:

- Exact reproduction of the frozen BUY_CALL underlying event graph.
- Immutable threshold, dataset, split, timing, cost, and ledger provenance.
- Causal next-completed-bar emission.
- Runtime fail-closed checks and deterministic idempotency.
- Shadow/advisory candidate evidence and focused tests.

Out of scope:

- No strategy-rule changes.
- No threshold or percentile changes.
- No graph timing, entry-delay, holding-period, cooldown, or research-cost changes.
- No historical ledger changes.
- No broker, order, execution, risk, live configuration, or dashboard changes.
- No option-premium profitability claim.
- No production-readiness or automatic-execution claim.

Boundary verification:

- [x] No broker path changed.
- [x] No order path changed.
- [x] No execution path changed.
- [x] No risk gate changed.
- [x] No live configuration changed.
- [x] Strategy remains shadow/advisory-only.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk path reviewed:

- `strategies/movement/market_event_graph_reversal.py`

Why this path is high risk:

- It creates a directional BUY_CALL candidate and therefore sits upstream of ranking, risk, approval, and potential execution consumers.
- Incorrect timing, stale evidence, weak provenance, or duplicate emission could create misleading operational signals.

Safety properties independently checked:

- Candidate promotion state is `ADVISORY_ONLY`.
- `allowed_for_live_execution` is false.
- `is_order_action` is false.
- `broker_api_called` is false.
- The graph requires strict consecutive completed rows.
- Entry is delayed to the next completed bar.
- Graph and entry bars must remain in one session.
- Timestamps and source-bar endpoints must be strictly increasing.
- Frozen dataset, specification, and threshold provenance are mandatory.
- Metadata cannot authorize test-threshold overrides.
- A deterministic SHA-256 triplet identity and caller-owned runtime state prevent repeated emission.

## Grill Me Review

Verdict: PASS

Questions challenged during review:

- Could an open-ended state machine accept non-consecutive events? The implementation was changed to strict consecutive-row matching.
- Could a candidate emit on the signal bar? The producer requires a later completed entry bar.
- Could a delayed signal cross a session boundary? All graph and entry bars must share the same session.
- Could duplicate source-bar endpoints create multiple logical bars? Strict source-bar ordering rejects them.
- Could runtime metadata replace the frozen thresholds? Override metadata is rejected.
- Could a growing cumulative history replay the same candidate? Persisted state and a deterministic triplet identity prevent re-emission.
- Could the result be presented as an option edge? The documentation explicitly preserves `NOT_OPTION_PREMIUM_VALIDATED`.

## Hermes Review

Verdict: PASS

Architecture findings:

- Frozen research evidence is separated from runtime detection.
- The breadth producer, live adapter, strategy, and immutable contract have distinct responsibilities.
- Runtime state is caller-owned rather than hidden in module globals.
- Candidate construction is completed before the emitted-state watermark advances.
- The runtime path fails closed when provenance, ordering, session identity, or coverage is invalid.

## GSD Review

Verdict: PASS

Delivery findings:

- The work remained limited to exact recovery, reproduction, shadow integration, fail-closed repair, evidence, and tests.
- No new strategy discovery or parameter tuning was mixed into the PR.
- The original historical results were reproduced before runtime publication.
- A separate independent branch recomputed thresholds, splits, trades, ledgers, and adversarial runtime cases.

## QA / Safety Review

Safety invariants:

```text
promotion_state = ADVISORY_ONLY
allowed_for_live_execution = false
is_order_action = false
broker_api_called = false
same_bar_entry = prohibited
threshold_override = prohibited
missing_or_invalid_evidence = no candidate
duplicate_graph_evaluation = no second candidate
```

Adversarial coverage includes:

- missing and wrong frozen specification hashes;
- changed thresholds;
- threshold-override metadata;
- insufficient constituent coverage;
- incomplete bars;
- duplicate and reversed timestamps;
- duplicate and reversed source-bar endpoints;
- mixed sessions and entry-session rollover;
- stale graph evidence;
- same-bar evaluation;
- repeated cumulative evaluation;
- a distinct later graph after the persisted watermark.

## Acceptance Proof

Independent publication result:

```text
PASS_PR746_SHADOW_PUBLICATION_GATE
```

Reproduced evidence:

```text
train occurrences = 168
validation trades = 115
validation PF = 2.4567905524018094
holdout trades = 25
holdout PF = 4.173855459438616
exact train ledger = match
exact validation ledger = match
exact holdout ledger = match
```

The independent audit also confirmed that the former runtime defects—duplicate source-bar endpoints, repeated evaluation, session-crossing pending entry, and metadata threshold injection—are rejected after the repair.

## Runtime Proof Required After Merge

Required operational proof after merge:

- Confirm that `completed_constituent_breadth_snapshots` reaches the adapter on every expected completed interval.
- Reconcile expected versus received intervals and constituent coverage.
- Record producer and adapter acceptance/rejection counts with reason codes.
- Confirm causal event labels and strict timestamp alignment from real feed data.
- Run a read-only shadow-observation campaign through candidate generation, Phase 1, Phase 2, ranking, UI, mock intent, and paper reconciliation.
- Validate the frozen signals against actual same-contract CE option rows before any paper/manual promotion.

## What This PR Does Not Prove

This PR does not prove:

- that live breadth input is currently supplied reliably;
- that the strategy will trigger during a live session;
- that a completed candidate will survive normal TradeBot gates;
- that an actual CE contract is profitable after spread, slippage, charges, and decay;
- that the historical holdout is an untouched independent certification set;
- that the strategy is ready for paper, manual live, or automatic execution;
- that the bearish mirror is valid;
- that production broker behaviour has been tested.

Truthful status remains:

```text
EXACT_UNDERLYING_DISCOVERY_REPRODUCED
PASS_PR746_SHADOW_PUBLICATION_GATE
NOT_OPTION_PREMIUM_VALIDATED
SHADOW_ADVISORY_ONLY
```

## Human Approval

Human approval is required before merge.

Approval must remain limited to merging the exact reproduced strategy as shadow/advisory infrastructure. It does not authorize paper orders, broker orders, live execution, threshold changes, or profitability claims.
