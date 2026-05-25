# Agent Review Evidence — PR #246 Advisory Entry Source Normalization

## Agent Work Contract

### Goal

Fix runtime advisory schema rejection caused by legacy `display_entry_source="compat"` rows reaching canonical advisory serialization.

### Files changed

- `core/review_queue.py`
- `tests/test_advisory_schema.py`
- `docs/agent_reviews/pr246_advisory_entry_source_normalization.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR246_ADVISORY_ENTRY_SOURCE_NORMALIZATION
decision: NORMALIZE_LEGACY_DISPLAY_ENTRY_SOURCE_BEFORE_SCHEMA_SERIALIZATION
reason: Runtime evidence after PR #245 showed advisory rows rejected with `invalid display_entry_source: compat`.
timestamp: 2026-05-25T06:45:31Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr246_advisory_entry_source_normalization.md

### Non-goals

- No strategy changes.
- No feed-health changes.
- No ranking/scoring changes.
- No broker calls.
- No order execution behavior.
- No websocket lifecycle changes.
- No latency threshold changes.

## Scope Guard

This PR only normalizes legacy display-only entry source metadata at the advisory emission schema boundary.

It does not make any candidate executable.

Invalid `execution_entry_source="compat"` remains invalid when paired with executable truth.

## Grill Me Review

### Pushback

Mapping `compat` blindly into an executable source would create false executable confidence.

### Required proof

- `display_entry_source="compat"` is normalized before schema serialization.
- `entry_source="compat"` is normalized consistently.
- `execution_entry_source="compat"` is not made executable.
- Existing advisory schema tests still pass.

## Hermes Review

### Contract clarity

Canonical advisory rows must use `ENTRY_SOURCE_ENUM`.

`compat` is treated as legacy display metadata only. It is preserved in `*_raw` audit fields and normalized to a canonical display source.

### Compatibility

No advisory schema enum is widened. The fix adapts legacy emission input to the existing canonical contract.

## GSD Review

### Minimality

The change is placed immediately before advisory serialization in `core.review_queue`.

### Determinism

The normalizer maps invalid display/entry sources deterministically using the existing `_display_entry_source_for_row(...)` helper.

## QA / Safety Review

Tests added:

- display-only `compat` is normalized and serializes successfully
- executable `compat` remains invalid and fails closed

Safety assertions:

- no broker calls
- no order action
- no executable promotion
- no live behavior change

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_advisory_schema.py tests/test_runtime_safety_boot_guard.py tests/test_security_guard.py -q
```

Expected:

- all selected tests pass
- no `display_entry_source="compat"` advisory schema failures in PAPER runtime

## Runtime Proof Required After Merge

Run PAPER live-market again and confirm:

- `advisory_queue_schema_error ... invalid display_entry_source: compat` no longer appears
- advisory rows are either emitted successfully or rejected for a different real blocker
- no broker orders are placed

## What This PR Does Not Prove

- It does not prove strategy edge.
- It does not prove feed freshness.
- It does not fix latency breaches.
- It does not create executable trades.
- It only fixes legacy advisory entry source schema compatibility.

## Human Approval

Proceed only if CI is green and the PR remains scoped to advisory schema-boundary normalization.
