# PR-OBS-14 — Trace Replay CLI

## Purpose

`replay_trace.py` replays serialized observability JSONL events by one identifier.

Supported identifiers:

```text
trace_id
candidate_id
cycle_id
```

## Commands

```bash
python scripts/replay_trace.py --input runtime/evidence/observability_events.jsonl --trace-id trace_123
python scripts/replay_trace.py --input runtime/evidence/observability_events.jsonl --candidate-id NIFTY_22500_CE_091531
python scripts/replay_trace.py --input runtime/evidence/observability_events.jsonl --cycle-id cycle_20260523_091531
python scripts/replay_trace.py --input runtime/evidence/observability_events.jsonl --candidate-id NIFTY_22500_CE_091531 --json
```

Exactly one identifier is accepted per run.

## Output

The replay output includes:

```text
filter_type
filter_value
event_count
summary
events
```

Events are ordered by timestamp, run, cycle, candidate, event name, and stage.

## Scope

```text
Read-only evidence helper.
No runtime startup.
No state writes.
No strategy changes.
No ranking changes.
No risk changes.
No dashboard dependency.
```

## Acceptance proof

```bash
python -m pytest tests/test_replay_trace.py
```

Tests cover candidate replay, blocked-path replay, stale-feed cycle replay, invalid-event failure, one-filter enforcement, miss-ing-target failure, and CLI text/JSON output.
