# Observability Safety Invariants

Status: PR-OBS-13  
Scope: tests-only safety invariant suite for existing observability contracts

## Purpose

PR-OBS-13 converts the observability layer into hard CI safety gates.

The goal is not to change trading behavior. The goal is to prove that existing observability contracts fail closed when unsafe or incomplete states are represented.

## Invariants

The test suite must fail if:

```text
fallback candidate becomes executable
stale feed candidate becomes executable
candidate has no terminal state
blocked candidate has no reason
candidate event has no candidate_id
decision event has no trace_id
paper mode marks an order action
paper mode marks a broker API call
observability wrapper changes business output
```

## Test files

```text
tests/observability/test_safety_invariants.py
tests/observability/test_candidate_lifecycle_contract.py
tests/observability/test_fallback_execution_block.py
tests/observability/test_stale_feed_execution_block.py
```

## What is protected

### Identity safety

Every decision event must include stable identity fields:

```text
run_id
cycle_id
trace_id
```

Candidate events must also include:

```text
candidate_id
```

### Reason safety

Blocked, downgraded, ignored, rejected, or suppressed decisions must include a reason.

This prevents silent no-trade decisions that cannot be debugged later.

### Fallback safety

Fallback quote data can be displayable for review, but it must not become executable.

The fallback safety report must keep:

```text
fallback_executable_count = 0
```

### Feed freshness safety

Stale feed data can be recorded for diagnostics, but stale-feed candidates must not become executable.

The feed freshness report must keep:

```text
stale_executable_count = 0
```

### Paper/live safety

Paper-mode observability records must not mark order-action or broker-call fields as true.

### Read-only observability safety

Observability wrappers must not mutate business outputs.

## Acceptance proof

Run:

```bash
python -m pytest \
  tests/observability/test_safety_invariants.py \
  tests/observability/test_candidate_lifecycle_contract.py \
  tests/observability/test_fallback_execution_block.py \
  tests/observability/test_stale_feed_execution_block.py

python scripts/validate_agent_review_evidence.py
```

## What this PR does not prove

This PR does not prove:

- live runtime emits complete events,
- every strategy has observability wiring,
- every runtime candidate reaches a terminal event,
- paper trading is stable,
- live trading is safe,
- ranking quality improved,
- profitability improved.

It only proves the existing observability contracts fail closed for unsafe or incomplete observability states.
