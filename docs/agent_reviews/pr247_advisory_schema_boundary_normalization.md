# Agent Review Evidence — PR #247 Advisory Schema Boundary Normalization

## Agent Work Contract

### Goal

Fix the remaining runtime advisory schema rejection after PR #246 where `display_entry_source="compat"` still reached advisory validation and serialization.

### Files changed

- `core/review_queue.py`
- `tests/test_advisory_schema.py`
- `docs/agent_reviews/pr247_advisory_schema_boundary_normalization.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR247_ADVISORY_SCHEMA_BOUNDARY_NORMALIZATION
decision: NORMALIZE_LEGACY_ENTRY_SOURCES_AT_ALL_ADVISORY_SCHEMA_BOUNDARIES
reason: Post-merge runtime proof after PR #246 still showed `advisory_queue_schema_error ... invalid display_entry_source: compat`; the remaining failure happens in advisory validation before emit.
timestamp: 2026-05-25T07:25:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr247_advisory_schema_boundary_normalization.md

### Non-goals

- No strategy changes.
- No feed-health changes.
- No ranking/scoring changes.
- No broker calls.
- No order execution behavior.
- No websocket lifecycle changes.
- No latency threshold changes.

## Scope Guard

This PR changes only the placement of the existing advisory entry-source normalizer.

It preserves the PR105 blocked lifecycle emit ordering:

```text
_normalize_blocked_candidate_lifecycle_schema(...)
_print_final_emit_truth(...)
```

The normalizer now runs at all advisory schema boundaries:

- before canonical advisory validation serialization
- before advisory emit serialization after late backfill
- before validation-failure diagnostic emission

## Grill Me Review

### Pushback

PR #246 had a valid normalizer but only covered one emit path. Runtime proof showed advisory validation can fail before `_emit_review_queue_logs(...)`, so the fix must cover `_build_canonical_advisory_entry(...)` as well.

### Required proof

- PR105 source-order assertion still passes.
- Final emit serialization runs normalization after late backfill.
- Canonical advisory validation runs normalization before `serialize_advisory_row(...)`.
- Validation-failure diagnostics are normalized before emission.
- `execution_entry_source="compat"` is not made executable.

## Hermes Review

### Contract clarity

Canonical advisory rows must not serialize with `display_entry_source="compat"` or `entry_source="compat"`.

`execution_entry_source="compat"` remains invalid when claiming executable truth.

### Compatibility

No advisory schema enum is widened. This PR only ensures legacy display metadata is normalized before canonical schema calls.

## GSD Review

### Minimality

One runtime ordering fix plus one regression test and one evidence file.

### Determinism

The existing deterministic normalizer is reused. No new source-mapping policy is introduced.

## QA / Safety Review

Safety assertions:

- no broker calls
- no order action
- no executable promotion
- no live behavior change
- no latency behavior change

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest   tests/test_blocked_candidate_lifecycle_schema_pr105.py::test_review_queue_normalizes_blocked_lifecycle_before_serialization   tests/test_advisory_schema.py   tests/test_runtime_safety_boot_guard.py   tests/test_security_guard.py   -q
```

## Runtime Proof Required After Merge

Run PAPER live-market again and confirm:

- `advisory_queue_schema_error ... invalid display_entry_source: compat` no longer appears
- `invalid entry_source: compat` no longer appears
- no broker orders are placed

## What This PR Does Not Prove

- It does not prove strategy edge.
- It does not fix feed freshness.
- It does not fix latency breaches.
- It does not create executable trades.
- It only fixes advisory schema-boundary normalization coverage.

## Human Approval

Proceed only if CI is green and runtime proof confirms the `compat` advisory schema error is gone.
