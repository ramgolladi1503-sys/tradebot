# PR-FEED-17 Resolution Read Model Agent Review

mode: REVIEW
candidate_id: pr_feed_17_resolution_read_model
decision: review_ready
reason: resolution_read_model_tests_docs
timestamp: 2026-05-27T19:02:00Z
source: pr_feed_17_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Scope

This review covers PR-FEED-17 only.

The PR adds a pure read-model helper for feed selection evidence. It returns dataclasses and dictionaries only.

## Allowed

- Add pure read-model helpers.
- Add focused tests.
- Add documentation and review evidence.
- Shrink `docs/EDGE_TODO.md`.

## Not Allowed

- No broker integration changes.
- No execution behavior changes.
- No runtime wiring.
- No dashboard or UI changes.
- No file writes from the helper.
- No cache reads from the helper.
- No hidden time or config reads from the helper.

## Review Notes

The helper has no network imports, no runtime state mutation, no logging side effects, and no file I/O.

The tests cover symbol normalization, exchange defaults, expiry parsing, ATM inference, option rank ordering, strike evidence, explicit failure reasons, per-symbol rows, combined maps, and payload shape.

## Acceptance Proof

Run:

```bash
pytest tests/test_pr_feed_17_resolution_read_model.py
```

CI must pass before merge.

## Next Action

After this PR is merged, continue with PR-FEED-18 only from the latest merged main commit.
