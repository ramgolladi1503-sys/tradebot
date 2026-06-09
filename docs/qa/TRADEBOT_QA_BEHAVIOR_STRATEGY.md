# Tradebot QA Behavior Strategy

## Purpose

This document locks the Tradebot QA system around intended product behavior, not around current implementation behavior.

Tradebot tests must not become a coverage museum. Every test must protect, prove, measure, or improve trading edge.

The test suite must answer one product question:

> Can Tradebot move from market data to candidate generation to ranking to manual-review readiness without lying about edge, safety, or profitability?

## Source of Truth

The source of truth for QA is product behavior:

- Fallback or recovered quote data is never executable.
- Stale feed blocks execution.
- Missing depth blocks execution when depth is required.
- Missing option proof blocks execution.
- Manual approval is required before any order path.
- Broker, network, and order paths are impossible inside tests unless explicitly mocked and proven safe.
- Dashboard and replay paths are read-only.
- Ranking must prove real score separation.
- Candidate pool and ranking must preserve all candidates but promote only valid candidates.
- No-trade is a valid product decision when evidence is weak, stale, unsafe, conflicted, or unprofitable.
- Tests must validate intended behavior even when current code violates it.

## Edge-First Test Law

Every Tradebot test must support at least one edge outcome:

1. Helps find better trades.
2. Stops bad trades.
3. Proves ranking quality.
4. Proves strategy expectancy.
5. Protects capital.
6. Prevents fake profitability.
7. Prevents stale, fallback, or fake data from becoming executable.
8. Improves replay and backtest truth.
9. Improves no-trade explainability.
10. Prevents dashboard or read-models from lying about edge.
11. Helps diagnose why edge is missing.

A test that only checks code shape, field existence, a random JSON round-trip, or current buggy behavior is not accepted unless it protects a real trading-edge contract.

Every new behavior, safety, regression, dashboard, replay, feed, ranking, candidate, strategy, or execution test should include an `Edge purpose` comment or docstring explaining why the test exists.

## QA Layers

### Unit Tests

Pure deterministic logic tests. They are valid only when the logic protects edge, safety, correctness, or profitability truth.

Examples:

- score calculations
- freshness calculations
- risk math
- expiry selection
- candidate identity normalization

### Component Tests

One module with realistic fake inputs.

Examples:

- candidate scoring
- no-trade engine
- candidate pool quality
- top opportunity selector
- execution truth classifier

### Integration Tests

Multiple internal modules wired together with broker/network blocked.

Examples:

- feed proof to candidate readiness
- strategy output to candidate pool to ranking
- ranking to dashboard read model
- no-trade evidence to dashboard surface

### Behavior Tests

Product truth tests.

Examples:

- fallback quote never becomes executable
- stale feed blocks executable candidate
- missing depth blocks executable candidate
- manual approval required before order path
- top opportunity table does not read raw emitted rows as truth

### Safety Tests

Fail-closed tests.

Examples:

- live flags cannot bypass test broker firewall
- real broker object cannot be used in tests
- real network calls fail fast
- order action flags remain false in dashboard/replay evidence

### Contract Tests

Schema and artifact compatibility tests.

Examples:

- candidate evidence schema
- ranking snapshot schema
- no-trade evidence schema
- dashboard read-model schema
- replay report schema

### Replay Tests

Offline deterministic historical tests.

Examples:

- replay cannot access future data
- replay cannot place orders
- replay cannot mutate live state
- same input produces same output

### UI / Read-Model Tests

Dashboard truth tests.

Examples:

- top executable table uses top opportunity snapshot
- raw rows stay debug-only
- fallback rows remain visible but non-executable
- stale snapshots are shown as stale

### Chaos / Destructive Tests

Bad input tests.

Examples:

- corrupt runtime artifact
- missing quote
- stale quote
- ask below bid
- negative LTP
- duplicate candidates
- conflicting CE/PE candidates

### Performance / Resource Tests

Small resource-budget tests that protect runtime viability.

Examples:

- ranking handles realistic candidate volume deterministically
- dashboard reader does not call heavy runtime paths
- replay does not mutate runtime state

## Test Acceptance Standard

Accepted tests prove behavior:

```python
assert report.executable_count == 0
assert "fallback" in report.rejected_opportunities[0].why_not_ranked
```

Rejected tests merely prove shape:

```python
assert isinstance(result, dict)
assert "score" in candidate
assert len(rows) == 3
```

## Non-Negotiable Boundaries

Tests must not:

- call real broker APIs
- create real orders
- open real WebSocket connections
- depend on live market data
- weaken production code
- add hidden test-only safety bypasses
- assert current buggy behavior as expected behavior

Tests may:

- use fail-fast fake brokers
- use deterministic market snapshots
- use temp runtime directories
- use offline replay fixtures
- use monkeypatching at external boundaries
- add dependency injection only when it improves safety and testability
