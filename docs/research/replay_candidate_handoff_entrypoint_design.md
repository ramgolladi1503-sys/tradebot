# Replay-only candidate handoff entrypoint design

## Goal

Add a replay-only entrypoint that can drive the existing runtime candidate handoff and candidate journal persistence path from real replay input, without broker, live orchestrator, or order side effects.

This is intentionally smaller than the live orchestrator path. It should prove the chain:

`replay input → normalized snapshot → StrategyContext → strategy → candidate → runtime_candidate_handoff_latest.json → candidate_journal.jsonl`

## Existing functions to reuse

Reuse existing production functions rather than reimplementing pipeline stages:

- `core.market_snapshot_builder.build_market_snapshot_from_raw_tick(...)`
- `core.runtime_snapshot_producer._strategy_context_from_market_symbol(...)`
- `core.ranking_orchestrator.build_ranked_opportunity_report(...)`
- `core.runtime_candidate_handoff.write_runtime_candidate_handoff_evidence(...)`
- `core.candidate_journal.write_candidate_journal_row(...)`
- `core.review_queue._write_review_queue_artifacts(...)` only if the replay runner needs to preserve the same review-queue persistence boundary
- Existing strategy callable(s), for example:
  - `strategies.movement.vwap_reclaim.generate_vwap_reclaim_rejection_candidates`

The replay entrypoint must not synthesize any candidate objects directly.

## Missing seams

The repository already has most stage primitives, but it lacks a public replay runner that connects them end to end.

The missing seam is a thin replay runner that can:

1. Load a real replay event from file.
2. Convert that event into a normalized snapshot.
3. Build `StrategyContext`.
4. Run the existing candidate generators.
5. Convert the ranked result into the payload expected by `write_runtime_candidate_handoff_evidence(...)`.
6. Persist candidate journal rows through the existing journal/review-queue path.

If the replay runner cannot obtain a single candidate handoff row from the ranked report without manual object construction, then a narrow adapter is required to map the ranked report payload into the handoff writer inputs.

That adapter should be read-only and should not change ranking, strategy, or gate decisions.

## Proposed command / script name

Recommended script:

```text
scripts/run_replay_candidate_handoff.py
```

Recommended usage:

```bash
python scripts/run_replay_candidate_handoff.py \
  --source <replay-input.jsonl-or-parquet> \
  --event-id <event-id-or-row-key> \
  --strategy-id <strategy-id> \
  --market-data <market-ticks.parquet> \
  --output-dir .runtime/replay_candidate_handoff
```

The script should default to writing the same runtime artifact names used by production:

- `.runtime/runtime_candidate_handoff_latest.json`
- `.runtime/candidates/candidate_journal.jsonl`

## Required input artifacts

Minimum required artifacts:

- A real replay source file that contains raw event input
- A market-data file for the same replay window, if the replay source does not already contain the quote fields needed by normalization
- A strategy identifier selecting an already-implemented strategy callable

Likely concrete inputs from the current repo:

- `.runtime/market_data/ticks_20260703.jsonl`
- `.runtime/market_data/ticks_20260703.parquet`
- `.runtime/market_data/ticks_*.parquet`
- existing replay event files already used by vertical-slice replay tooling

The runner must fail closed if the source file does not contain enough data to build a real normalized snapshot.

## Output artifacts

The script must default to an isolated replay output directory and only write production-style artifact names inside that directory.

Default: `.runtime/replay_candidate_handoff/<run_id>/`

Artifacts:

- `.runtime/replay_candidate_handoff/<run_id>/runtime_candidate_handoff_latest.json`
- `.runtime/replay_candidate_handoff/<run_id>/candidate_journal.jsonl`
- a replay audit report under `.runtime/replay_candidate_handoff/<run_id>/` or `docs/research/`

It must not overwrite:

- `.runtime/runtime_candidate_handoff_latest.json`
- `.runtime/candidates/candidate_journal.jsonl`

unless an explicit `--write-production-artifacts` flag is provided, and that flag should be forbidden in tests.

Optional but recommended for debugging:

- a per-run audit JSON
- a markdown evidence report

## Safety flags

The replay runner must emit explicit safety flags on its own report payload:

- `replay_only=true`
- `broker_api_called=false`
- `order_action=false`
- `live_feed_used=false`
- `append=false`
- `output_isolated=true`
- `production_artifacts_written=false`

It should also inherit the existing read-only flags from the runtime evidence payloads:

- `read_only=true`
- `append=false` for the handoff evidence payload
- `is_order_action=false`

## Stage evidence to capture

The runner should emit one evidence record per stage, with the following minimum fields:

- replay event id
- source file and source timestamp
- normalized snapshot evidence
- `StrategyContext` creation evidence
- strategy invocation evidence
- candidate emission or explicit rejection reason
- ranking outcome or ranking rejection reason
- handoff persistence path
- journal persistence path

The evidence should be enough to prove whether the chain reached each stage naturally.

## Failure modes

The runner should fail closed with explicit reasons:

- `BLOCKED_NO_REPLAY_INPUT`
  - no usable replay event or market replay artifact exists
- `BLOCKED_NO_NORMALIZED_SNAPSHOT`
  - raw event exists but normalization cannot build a valid snapshot
- `BLOCKED_NO_STRATEGY_CONTEXT`
  - normalized snapshot exists but `StrategyContext` cannot be built
- `BLOCKED_NO_CANDIDATE`
  - strategy returns no candidate for the replay event
- `BLOCKED_RANKING_REJECTED`
  - strategy candidate exists but ranking rejects promotion
- `BLOCKED_NO_PERSISTENCE`
  - candidate exists but handoff/journal artifacts cannot be written

These are evidence states, not bugs to suppress.

## Tests needed

Add focused tests for the replay runner and its adapters:

1. Replay input produces a normalized snapshot from a real fixture.
2. Normalized snapshot produces a `StrategyContext`.
3. Strategy invocation is real and does not manually instantiate candidate objects.
4. Candidate handoff writer receives a real ranked payload.
5. Candidate journal writer persists the same replay row.
6. Replay-only flags are present and broker/order/live flags remain false.
7. The runner fails closed with each blocker mode above.
8. The runner does not claim success when ranking rejects the candidate.

## Why this is not the same as `main.py --run-once`

`main.py --run-once` enters the live orchestrator loop. That path is coupled to live monitoring, live feed state, and the existing runtime control flow.

The replay-only entrypoint must:

- read real replay artifacts instead of live feed state
- avoid the live loop entirely
- avoid broker wiring
- avoid order placement paths
- avoid live feed mutation
- remain read-only and fail closed when replay data is insufficient

So the replay entrypoint is a separate proof harness around the same runtime primitives, not a shortcut through the live app.

## Design summary

The smallest viable implementation is a thin replay runner script plus one narrow adapter if needed to map a ranked report into the existing handoff/journal writers.

The runner should reuse existing normalization, context creation, strategy, ranking, handoff, and journal functions as-is.
It should not invent candidates, and it should not relax any gates.
