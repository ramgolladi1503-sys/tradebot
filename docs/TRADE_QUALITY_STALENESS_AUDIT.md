# Tradebot stale feed and executable quality audit

Branch: `hardening/main-stale-executable-quality`  
Base: `main`

## Findings

### 1. Token resolution could crash instead of failing closed

`core/option_token_resolver.py` tried to build a fallback payload even when no safe fallback contract existed. That means an unresolved option contract could raise an exception instead of returning `None` and logging `OPTION_TOKEN_NOT_FOUND`.

Impact:

- candidate pipeline can lose otherwise valid symbols because one unresolved contract crashes resolution
- dashboard/feed state can show `NO_TOKEN` or zero executable symbols
- execution quality becomes noisy because the system cannot clearly separate no-contract from bad-signal

Fix applied in this branch:

- fallback payload is returned only when a safe fallback is actually found
- when no fallback exists, the resolver logs `OPTION_TOKEN_NOT_FOUND` and returns `None`
- no fake contract is created

### 2. Confidence-only execute promotion is too permissive

`core/decision_engine.py` currently allows direct `EXECUTE` promotion when `gating_confidence` crosses promotion thresholds. That is not elite behavior. Confidence alone is not enough.

A real executable candidate must also prove:

- healthy feed state
- valid execution quality
- acceptable fill probability
- valid risk/reward geometry
- sufficient final score
- sufficient raw rank
- non-fallback, non-synthetic truth quality

Recommended next patch:

- add an `elite_execute_context` predicate
- require it before any `EXECUTE` branch
- route high-confidence-but-incomplete rows to `QUEUE_ONLY` with reason `confidence_without_full_execution_quality`

### 3. Feed freshness has split sources and tight windows

The code reads freshness from:

- decision telemetry rows
- runtime feed snapshot JSON
- runtime feed DB row
- tick DB age
- local WebSocket memory

This is good for observability but dangerous if precedence is inconsistent. The decision DAG should be the single source of truth once active. Runtime snapshots should only bootstrap readiness before fresh decision rows exist.

Recommended next patch:

- add a feed truth snapshot object with canonical selected source
- expose source, age, state, blockers, subscribed option count, and last option tick age by symbol
- fail closed only during market open + live quote required

### 4. Trade quality is low because executable is not equal to tradable edge

The bot currently mixes these concepts too easily:

- candidate interestingness
- signal confidence
- data truth
- feed freshness
- execution quality
- actual tradability

Elite version must keep them separate.

Minimum contract:

- `ADVISORY_ONLY`: interesting but not executable
- `QUEUE_ONLY`: structurally valid but missing one or more execution requirements
- `EXECUTE`: real contract + live quote + healthy spread/liquidity + valid levels + sufficient final edge

## Immediate branch status

Implemented:

- token resolver fallback fail-closed fix

Still required:

- decision engine execute-promotion hardening
- canonical feed truth snapshot
- tests for fallback miss, confidence-only promotion, feed degraded queue-only, and stale quote blocking
