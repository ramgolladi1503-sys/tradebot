# Agent Review Evidence — PR-FEED-05 Exact Option Token Freshness Gate

## Agent Work Contract

### Goal

Add a read-only exact option-token freshness gate that blocks executable ranking output when option token evidence is absent, mismatched, or stale.

### Files changed

- `core/exact_option_token_freshness_gate.py`
- `tests/test_pr_feed_05_exact_option_token_freshness_gate.py`
- `docs/PR_FEED_05_EXACT_OPTION_TOKEN_FRESHNESS_GATE.md`
- `docs/agent_reviews/pr_feed_05_exact_option_token_freshness_gate.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_05_EXACT_OPTION_TOKEN_FRESHNESS_GATE
decision: READ_ONLY_EXACT_OPTION_TOKEN_FRESHNESS_GATE
reason: Exact option-token freshness blocks executable ranking output when token identity is absent, mismatched, stale, or incomplete.
timestamp: 2026-05-24T20:04:32Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_05_exact_option_token_freshness_gate.md

### Non-goals

- No token-selection changes.
- No token resolver rewrite.
- No option-chain rewrite.
- No websocket refactor.
- No reconnect logic.
- No resubscribe logic.
- No subscription changes.
- No strategy changes.
- No dashboard UI changes.
- No external adapter changes.
- No order intent.

## Grill Me Review

### Pushback

A candidate can look executable while pointing at the wrong option token. That can make the system rank a contract different from the intended expiry, strike, or side.

### Required proof

- Expected/observed token mismatch must emit zero ranks.
- Absent token must fail closed.
- Absent tick age must fail closed.
- Stale tick age must fail closed.
- Multiple records must fail if any one record is unsafe.
- Exact fresh evidence must preserve normal ranking behavior.

## Hermes Review

### Contract clarity

The gate consumes explicit evidence only. It does not resolve tokens, select contracts, subscribe instruments, or mutate candidate state.

### Serialization

The decision object provides `to_dict()` and `to_json()`. Serialized output includes `is_order_action=false` without direct mutable dataclass field assignment.

## GSD Review

### Determinism

Tests use fixed token evidence and tick ages. No wall-clock dependency is required.

### Minimality

The PR adds one pure/read-only module and focused tests. It does not alter feed runtime, ranking internals, strategy behavior, token resolution, websocket behavior, or dashboard UI.

## QA / Safety Review

### Safety assertions

Tests assert:

- `read_only=True`
- `is_order_action=False`
- `append=False`
- `rank_count=0` while blocked
- `executable_count=0` while blocked
- no ranks while blocked

### Negative coverage

- Token mismatch.
- Absent observed token.
- Absent token identity.
- Absent tick age.
- Stale tick age.
- Mixed multi-record evidence with one unsafe token.

## Scope Guard

Confirmed not touched:

- Token resolver implementation.
- Option-chain selection.
- Websocket lifecycle.
- Reconnect/resubscribe behavior.
- Strategy code.
- Dashboard UI.
- External adapters.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_05_exact_option_token_freshness_gate.py
```

Expected:

- Exact fresh token evidence allows ranking.
- Absent/mismatched/stale token evidence blocks ranking.
- CI and repo gates green before merge.

## Runtime Proof Required After Merge

Before wiring this into runtime, capture real runtime evidence showing:

- expected token
- observed token
- symbol identity
- expiry/strike/option side where available
- tick age
- max allowed tick age

This PR only defines the read-only contract. It does not claim runtime wiring exists.

## What This PR Does Not Prove

- It does not prove token resolver correctness.
- It does not prove option-chain selection correctness.
- It does not prove websocket subscription correctness.
- It does not prove strategy edge.

## Human Approval

Proceed only if CI is green and the PR remains limited to read-only exact option-token freshness gating.


## High-Risk Path Review

N/A
