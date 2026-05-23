# PR-OBS-14 — Trace Replay CLI Agent Evidence

```yaml
mode: paper_review
timestamp: 2026-05-23T08:45:00Z
candidate_id: pr_obs_14_trace_replay_cli
decision: approve_scoped_trace_replay_cli
reason: deterministic_read_only_observability_replay
is_order_action: false
broker_api_called: false
source: docs/observability/TRACE_REPLAY.md
```

## Agent Work Contract

Build the scoped PR-OBS-14 trace replay CLI only.

Files in scope:

```text
scripts/replay_trace.py
tests/test_replay_trace.py
docs/observability/TRACE_REPLAY.md
docs/agent_reviews/pr_obs_14_trace_replay_cli.md
```

## Scope Guard

Allowed:

```text
Read observability JSONL events.
Replay by trace_id, candidate_id, or cycle_id.
Return deterministic text or JSON output.
Validate event payloads through the existing observability schema.
Add focused tests and docs.
```

Not allowed:

```text
Runtime startup.
State writes.
Strategy changes.
Ranking changes.
Risk changes.
Dashboard changes.
External integration changes.
```

## Grill Me Review

Risk: replay could silently accept malformed events.
Mitigation: invalid events raise a trace replay error through existing event validation.

Risk: output ordering could be unstable.
Mitigation: events are sorted by timestamp, run, cycle, candidate, event name, and stage.

Risk: CLI could mix multiple replay targets.
Mitigation: exactly one identifier is accepted.

## Hermes Review

The CLI is deterministic and reviewable. It uses plain JSONL input and has no runtime side effects.

## GSD Review

This PR improves post-run debugging by making one trace, candidate, or cycle inspectable from evidence events.

## QA / Safety Review

Acceptance command:

```bash
python -m pytest tests/test_replay_trace.py
```

Coverage:

```text
Candidate replay.
Blocked-path replay.
Stale-feed cycle replay.
Invalid event failure.
One-filter enforcement.
Missing-target failure.
CLI JSON output.
CLI text output.
```

## Human Approval

Ready for PR review after CI passes.
