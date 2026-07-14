# PR-FEED-13 — Candidate Pipeline Feed Hold Integration

## Purpose

PR-FEED-13 wires canonical feed-health truth into the ranked opportunity pipeline.

The feed-hold gate already existed as a read-only contract. This PR connects it to `build_ranked_opportunity_report(...)` so candidate ranking can be held when callers provide canonical feed-health truth.

## Scope

In scope:

- Add optional `feed_health` input to `build_ranked_opportunity_report(...)`.
- Route ranking through the existing `apply_feed_hold_to_ranking(...)` only when feed truth is provided.
- Keep legacy behavior unchanged when no feed truth is supplied.
- Surface feed-gate metadata in the pipeline report.
- Add tests proving unhealthy feed truth holds ranking output and healthy feed truth preserves ranking.

Out of scope:

- No feed lifecycle changes.
- No reconnect logic.
- No resubscribe logic.
- No token-selection changes.
- No strategy changes.
- No dashboard UI changes.
- No threshold tuning.

## Contract

New optional parameter:

```python
build_ranked_opportunity_report(..., feed_health=None)
```

Behavior:

- `feed_health is None`: legacy ranking path remains unchanged.
- healthy feed truth: ranking is preserved.
- unhealthy feed truth: ranking report is held with zero ranked/executable output using the existing feed-hold gate.

Pipeline stage order now explicitly includes:

```text
feed_hold_gate
```

## Acceptance proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_ranking_orchestrator.py tests/test_pr_feed_03_feed_hold_gate.py
```

Expected:

- Existing ranking orchestrator behavior remains compatible.
- Unhealthy feed truth produces zero ranked output.
- Healthy feed truth preserves ranking output.
- Feed-hold metadata appears in the pipeline report only when active.

## Runtime Proof Required After Merge

After merge, run a paper-mode runtime snapshot/candidate cycle and confirm:

- pipeline reports include `feed_health_input_present=true` when feed truth is supplied.
- unsa-fe feed truth results in `feed_hold_active=true`.
- unsafe feed truth produces zero ranked output.
- healthy feed truth preserves normal ranking behavior.
- no strategy/feed lifecycle behavior changes were introduced.

## Next PR

After this PR is merged and green, continue only to the next scoped feed-readiness step.
