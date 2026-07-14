# PR-FEED-12 — Wire Canonical Feed Decision Into Runtime Snapshots

## Purpose

PR-FEED-12 exposes the canonical feed-health truth decision in runtime snapshots.

Before this PR, the runtime snapshot producer copied `feed_runtime_latest` into `runtime/feed_runtime_latest.json`, but did not also publish the canonical reconciled `FeedHealthTruthDecision` that downstream readers can consume consistently.

## Scope

In scope:

- Derive `feed_health_truth_latest` from the existing `feed_runtime_latest` payload.
- Write the derived payload to `runtime/feed_health_truth_latest.json` through the existing atomic snapshot writer.
- Return the new payload in `produce_and_store_runtime_snapshots(...)` outputs.
- Keep payload read-only and non-action.
- Add focused tests for healthy, unhealthy, invalid, and runtime-unsafe feed evidence.

Out of scope:

- No websocket lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No subscription changes.
- No token-selection changes.
- No strategy changes.
- No dashboard UI changes.
- No external execution behavior.
- No order intent.

## Snapshot contract

New output key:

```text
feed_health_truth_latest
```

New snapshot path:

```text
runtime/feed_health_truth_latest.json
```

Payload fields:

- `schema_version`
- `read_only`
- `i-s_order_action`
- `append`
- `source_snapshot`
- `source_payload_present`
- `feed_health_truth`
- `feed_ok`
- `blockers`
- `metadata`

## Why this matters

The feed-hardening chain now has a canonical runtime-visible feed decision:

1. Raw feed runtime evidence remains available as `feed_runtime_latest`.
2. Reconciled feed truth becomes available as `feed_health_truth_latest`.
3. Downstream PRs can consume one deterministic feed-health truth instead of re-interpreting raw feed payload fields repeatedly.

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_pr_feed_12_runtime_snapshot_feed_decision.py
```

Expected:

- Healthy feed evidence emits `feed_ok=true` and no blockers.
- Unhealthy feed evidence emits `feed_ok=false` and canonical blockers.
- Invalid feed payload fails closed.
- Unsafe runtime state fails closed.
- Snapshot payload remains read-only and non-action.

## Next PR

After this PR is merged and green, continue only to the next scoped feed-readiness step:

```text
PR-FEED-13 — Candidate Pipeline Feed Block Integration
```
