# OOS context contract design

## Verdict

`REPLAY_CONTEXT_PARTIAL`

The remaining replay-context blockers are a real gap, but they do not require inference. The explicit source for `is_oos` and `oos_label` should be the replay/WFA run configuration and partition metadata, not the source artifact filename or date.

## What is already true

The current replay and journal paths already preserve OOS values when they are present in the runtime payload:

- `core.replay_context_recorder.build_replay_context_record(...)` accepts `is_oos` and `oos_label`
- `core.candidate_journal.build_candidate_journal_row(...)` preserves `is_oos`, `oos_label`, and records `oos_source`
- `core.replay_candidate_handoff_entrypoint.run_replay_candidate_handoff(...)` forwards `is_oos` and `oos_label` from the replay row into the top candidate and runtime handoff payload when present
- `core.option_backtest.wfa.run_option_replay_wfa(...)` already has explicit train / validation / holdout partitions and labels the final certification verdict based on those partition boundaries

The missing piece is not a derivation heuristic. The missing piece is an explicit partition-context payload that is attached to replay rows and carried through the recorder chain.

## Minimal explicit OOS source

The OOS source should be carried as a small contract object attached to replay input and validation runs:

```json
{
  "is_oos": true,
  "oos_label": "OOS",
  "oos_source": "wfa_partition_context",
  "partition_id": "holdout",
  "split_name": "holdout"
}
```

### Semantics

- `is_oos`
  - boolean, explicit, never inferred from dates
- `oos_label`
  - one of `IS` / `OOS`
  - must match the run partition context
- `oos_source`
  - required provenance string
  - recommended value for WFA / certification runs: `wfa_partition_context`
- `partition_id`
  - optional stable identifier for the current partition
- `split_name`
  - optional human-readable split name

If the replay source is not attached to an explicit partition context, both `is_oos` and `oos_label` must remain null in the recorder/journal chain and the run must stay blocked for strict certification.

## Smallest contract boundary

The minimal place to inject explicit OOS context is the replay run configuration / partition metadata layer used by:

- `core/option_backtest/wfa.py`
- the replay candidate handoff runner
- the strict export / journal recorder path

Recommended shape:

1. WFA config builds a partition plan.
2. Each partition produces an explicit context payload:
   - `partition_id`
   - `split_name`
   - `is_oos`
   - `oos_label`
   - `oos_source`
3. Replay runner attaches that payload to:
   - replay context bundle
   - runtime handoff evidence
   - candidate journal row
4. Strict export accepts OOS only if the payload is present and internally consistent.

This avoids guessing and keeps the source of truth at the run boundary.

## Fail-closed behavior

When OOS context is missing:

- `is_oos = null`
- `oos_label = null`
- `oos_source = "unknown_runtime_context"`
- `replay_context_ready = false`
- `replay_context_blockers` includes:
  - `missing_is_oos`
  - `missing_oos_label`
  - `missing_oos_context_source`

For WFA certification:

- a partition run without explicit OOS context must not be promoted to certification-candidate status
- a replay row with unknown OOS context must fail closed, not default to in-sample

## Flow through the existing system

### Replay context bundle

The bundle recorder should preserve the explicit OOS context payload if present:

- `is_oos`
- `oos_label`
- `oos_source`
- `partition_id`
- `split_name`

If absent, the bundle should record blockers only.

### Candidate journal

Candidate journal rows should continue to preserve `is_oos` / `oos_label` when explicitly provided.

If the source lacks them:

- keep them null
- set `oos_source="unknown_runtime_context"`
- keep `strict_replay_export_ready=false`

### Strict export

Strict export should require explicit OOS context for certification-ready replay rows.

Allowed:

- export with OOS metadata present and consistent with the partition context

Blocked:

- export that invents OOS from filename, date range, or run name
- export that silently marks unknown rows as IS

### Option replay WFA

WFA partitions already define the correct semantic boundary.

Required rule:

- `train` -> `is_oos=false`, `oos_label=IS`
- `validation` -> `is_oos=false`, `oos_label=IS` unless the workflow explicitly defines validation as OOS for a specific downstream contract
- `holdout` -> `is_oos=true`, `oos_label=OOS`

The exact mapping must be encoded in the run config, not inferred ad hoc in the replay path.

## Why this is the right seam

- It is explicit.
- It is reproducible.
- It does not depend on filenames.
- It keeps replay, journal, strict export, and WFA aligned.
- It preserves fail-closed behavior for certification.

## Conclusion

The smallest honest fix is to add an explicit partition-context payload to replay/WFA run configuration and carry it through the recorder chain. Until that exists, OOS must remain blocked rather than inferred.
