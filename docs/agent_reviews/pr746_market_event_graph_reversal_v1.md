# PR 746 — Frozen Market Event Graph Reversal V1

mode: PAPER
candidate_id: pr746-market-event-graph-reversal-v1
decision: REVIEW_ONLY
reason: exact frozen underlying-event reproduction with fail-closed shadow advisory output
timestamp: 2026-07-30T03:10:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr746_market_event_graph_reversal_v1.md

## Agent Work Contract

```text
source_agent: ChatGPT and Codex with independent audit
implementation_head_before_ci_repair: c65075f5922ccf37dde265419244df877ef104da
independent_audit_commit: 2e1913b5758b22e6f32ce27fb357d4d79a1e9735
action: REVIEW_AND_PUBLISH_SHADOW_ONLY
scope: recover and reproduce the frozen market-event graph, enforce causal timing and immutable provenance, and publish only a non-executable advisory candidate
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
acceptance_proof:
  - source archive and dataset hashes match the frozen evidence
  - train-only thresholds and chronological split match independently
  - train, validation, and holdout ledgers match independently
  - graph timing is strict A(t-2) -> B(t-1) -> C(t)
  - entry requires the next completed bar
  - invalid provenance, ordering, coverage, freshness, or session identity emits nothing
  - persisted runtime state prevents duplicate emission
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
- Runtime rejection checks and deterministic idempotency.
- Shadow candidate evidence and focused tests.

Out of scope:

- No strategy-rule, threshold, percentile, graph-timing, delay, holding-period, cooldown, or cost changes.
- No historical-ledger changes.
- No broker, order, execution, risk, live-configuration, or dashboard changes.
- No option-premium, production-readiness, or automatic-execution claim.

Boundary verification:

- [x] Broker, order, execution, risk, live configuration, and dashboard paths were not changed.
- [x] The strategy remains shadow/advisory-only.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

Reviewed high-risk path:

- `strategies/movement/market_event_graph_reversal.py`

This path creates a directional candidate upstream of ranking and approval. The review confirmed strict completed-row timing, one-bar delay, single-session enforcement, immutable provenance, deterministic idempotency, advisory-only promotion, and explicit non-action evidence:

```text
allowed_for_live_execution = false
is_order_action = false
broker_api_called = false
```

## Grill Me Review

Verdict: PASS

The review challenged non-consecutive matching, same-bar entry, session rollover, duplicate source-bar endpoints, metadata threshold overrides, cumulative-history replay, and overstatement of option economics. Focused tests and the independent audit cover each of those failure modes.

## Hermes Review

Verdict: PASS

The breadth producer, immutable contract, adapter, strategy, and reproduction evidence have separate responsibilities. Runtime state is caller-owned, no module-global replay cache is used, and the emitted watermark advances only after candidate construction.

## GSD Review

Verdict: PASS

The delivery remained limited to recovery, exact reproduction, shadow integration, runtime rejection hardening, evidence, and tests. It did not restart discovery or tune around the historical result.

## QA / Safety Review

Verified invariants:

```text
promotion_state = ADVISORY_ONLY
allowed_for_live_execution = false
is_order_action = false
broker_api_called = false
same_bar_entry = prohibited
threshold_override = prohibited
invalid_or_absent_evidence = no candidate
repeated_graph_evaluation = no second candidate
```

Coverage includes absent or incorrect provenance, changed thresholds, override attempts, inadequate constituent participation, incomplete bars, timestamp and source-end ordering defects, mixed sessions, entry rollover, stale evidence, same-bar evaluation, repeated evaluation, and a later distinct graph.

## Acceptance Proof

Independent publication result:

```text
PASS_PR746_SHADOW_PUBLICATION_GATE
```

Independent evidence result:

```text
train occurrences = 168
validation trades = 115
validation PF = 2.4567905524018094
holdout trades = 25
holdout PF = 4.173855459438616
train ledger = exact match
validation ledger = exact match
holdout ledger = exact match
```

The post-repair audit confirmed rejection of duplicate source-bar endpoints, repeated evaluation, cross-session delayed entry, and metadata threshold injection.

## Runtime Proof Required After Merge

After merge, operational evidence must confirm that completed constituent breadth rows reach the adapter at each expected interval, timestamps align, producer and adapter rejection reasons reconcile, causal labels are generated from real feed data, and the candidate preserves identity through TradeBuilder, Phase 1, Phase 2, ranking, UI, mock intent, and paper reconciliation.

Actual same-contract CE rows with causal fills and complete costs must be evaluated separately before any paper or manual-live promotion.

## What This PR Does Not Prove

This PR does not prove live breadth availability, live trigger frequency, gate survival, dashboard delivery, actual CE profitability, untouched prospective certification, bearish-mirror validity, production broker behaviour, paper eligibility, or live eligibility.

Truthful state:

```text
EXACT_UNDERLYING_DISCOVERY_REPRODUCED
PASS_PR746_SHADOW_PUBLICATION_GATE
NOT_OPTION_PREMIUM_VALIDATED
SHADOW_ADVISORY_ONLY
```

## Human Approval

Human approval is required before merge. Approval is limited to shadow/advisory infrastructure and does not authorize paper orders, broker orders, live execution, threshold changes, or profitability claims.
