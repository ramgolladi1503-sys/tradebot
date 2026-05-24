# PR-FEED-05 — Exact Option Token Freshness Gate

## Purpose

PR-FEED-05 adds a small read-only gate that validates exact option-token evidence before executable ranking output is allowed.

The goal is to ensure a candidate is not treated as executable when the observed option token is missing, mismatched, or stale against the expected option token identity.

## Scope

In scope:

- Add `core/exact_option_token_freshness_gate.py`.
- Consume explicit option-token evidence supplied by callers.
- Validate:
  - symbol identity
  - expected token
  - observed token
  - token match
  - last tick age
- Return zero-rank, zero-executable ranking output when token evidence is unsafe.
- Preserve normal ranking when token evidence is exact and fresh.
- Add negative tests for missing, mismatched, stale, and partially unsafe token evidence.

Out of scope:

- No token-selection changes.
- No token resolver rewrite.
- No option-chain rewrite.
- No websocket refactor.
- No reconnect logic.
- No resubscribe logic.
- No subscription changes.
- No strategy changes.
- No dashboard UI changes.
- No broker calls.
- No order intent.
- No live execution behavior.

## Contract

`classify_exact_option_token_freshness(token_evidence, max_tick_age_sec=...)` returns read-only evidence:

- `gate_active=false` when all token records are exact and fresh.
- `gate_active=true` when token evidence is missing.
- `gate_active=true` when expected and observed tokens differ.
- `gate_active=true` when token tick age is missing.
- `gate_active=true` when token tick age exceeds the configured freshness threshold.
- `is_order_action=false`.
- `append=false`.

`apply_exact_option_token_freshness_to_ranking(scores, token_evidence, ...)` returns:

- Existing normal ranking when token evidence is exact and fresh.
- Zero ranks and zero executable count when token evidence is unsafe.
- `exact_option_token_freshness` safety flag when blocked.
- Source score count in metadata for traceability.

## Negative cases proved

Tests prove:

1. Exact fresh token evidence is read-only and non-action.
2. Token mismatch suppresses executable ranking output.
3. Stale token tick age suppresses executable ranking output.
4. Missing token tick age fails closed.
5. Missing token fails closed.
6. Missing token identity fails closed.
7. Fresh evidence preserves normal ranking order.
8. Multiple token records fail if any one record is unsafe.
9. Evidence is JSON serializable and non-action.

## Acceptance criteria

- Exact option-token freshness gate is read-only.
- No token resolver, websocket, subscription, strategy, dashboard, or broker behavior is changed.
- Missing/mismatched/stale token evidence cannot emit executable ranked output.
- Fresh exact token evidence preserves existing ranking behavior.
- CI and repo gates are green.

## Next PR

After this PR is merged and green, continue to the next scoped feed-readiness step only:

```text
PR-FEED-12 — Wire Canonical Feed Decision Into Runtime Snapshots
```

Do not broaden into websocket rewrites, strategy rebuilds, dashboard UI, or live order behavior.
