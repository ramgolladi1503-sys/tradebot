# Replay context bundle recorder

## Verdict

`REPLAY_CONTEXT_BUNDLE_PARTIAL`

The replay runner now writes isolated replay-context bundle artifacts that capture the real runtime inputs around each replay row. This does not prove natural candidate emission yet. It gives the next proof step a durable bundle of inputs without synthesizing candidates or mutating production artifacts.

## What it records

Each bundle records:

- `replay_bundle_id`
- `replay_event_id`
- `source_path`
- `source_row_index`
- `source_timestamp` / `source_timestamp_epoch` when present
- `source_file_sha256` and `source_row_sha256` when available
- the normalized snapshot used for `StrategyContext`
- the `StrategyContext` input payload
- feed-truth / regime / quote-truth fields when present
- strategy/report summaries when available
- `replay_context_ready` and `replay_context_blockers`
- `replay_context_bundle_ready` and `replay_context_bundle_blockers`

## Safety

- No broker calls.
- No live execution.
- No order placement.
- No candidate synthesis.
- No overwrite of production runtime artifacts in tests.

## Output layout

Default isolated output:

- `.runtime/replay_context_bundles/<run_id>/replay_context_bundle_latest.json`
- `.runtime/replay_context_bundles/<run_id>/replay_context_bundle_<bundle_id>.json`

The replay handoff artifacts remain under the separate replay-handoff tree.

## Current limit

The bundle recorder does not yet prove that the replay input is rich enough to naturally emit a candidate. It only makes the miss-ing context explicit and durable.
