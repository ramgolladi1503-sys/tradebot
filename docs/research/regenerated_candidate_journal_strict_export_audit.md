# Regenerated candidate journal strict export audit

Date: 2026-07-12

## Verdict

`PARTIALLY_PROVEN_FROM_EXISTING_RUNTIME_HANDOFF`

This audit proves the journal writer now persists strict-replay metadata fields when given an existing runtime candidate handoff artifact. It does not prove that a fresh replay entrypoint regenerated the candidate through strategy execution.

## What was regenerated

A single candidate journal row was regenerated from the real runtime artifact:

- Source: `.runtime/runtime_candidate_handoff_latest.json`
- Runtime snapshot field used: `top_reportable_executable_snapshot`
- Runtime metadata carried through: `generated_epoch`, `source`, `metadata`, `symbol`, `top_reportable_executable_trade_id`
- Output journal row written to: `/tmp/regenerated_candidate_journal.jsonl`

This used the existing journal writer only. No strategy logic, ranking logic, broker logic, or WFA certification was run.

## Persisted strict-replay fields on the regenerated row

The regenerated row now carries explicit strict-replay metadata fields:

- `feature_cutoff_ts`: `null`
- `signal_ts`: `2026-07-12T13:58:11.615200Z`
- `earliest_entry_ts`: `null`
- `is_oos`: `null`
- `oos_label`: `null`
- `strict_replay_export_ready`: `false`
- `strict_replay_export_blockers`: `["missing_feature_cutoff_ts", "missing_earliest_entry_ts", "missing_is_oos", "missing_oos_label"]`

Field sources:

- `signal_ts` was preserved from the runtime journal writer’s `created_at` boundary, which is derived from the write timestamp of the runtime journal row.
- `feature_cutoff_ts` stayed null because the source runtime artifact did not provide an explicit feature cutoff or snapshot timestamp.
- `earliest_entry_ts` stayed null because the source runtime artifact did not provide an explicit eligible-entry timestamp.
- `is_oos` and `oos_label` stayed null because the runtime context was not a WFA partition context.

## Strict export audit result

Command used:

```bash
python scripts/export_strict_option_replay_wfa.py --source /tmp/regenerated_candidate_journal.jsonl --market-data .runtime/market_data/ticks_20260703.parquet --audit-json /tmp/regenerated_candidate_journal_audit.json
```

Result:

- `ok: false`
- blocked fields included:
  - `feature_cutoff_ts`
  - `earliest_entry_ts`
  - `is_oos`
  - `oos_label`
  - plus contract/market fields not present on this regenerated row

Important change relative to the previous readiness report:

- The new journal row explicitly persists strict-replay metadata fields instead of omitting them.
- The export remains blocked honestly because the real source runtime artifact still lacks the timing/OOS data and the option contract/market fields required by the strict export contract.
- The blocker set is smaller than before in one respect: `signal_ts` is now present on the regenerated journal row.

## Interpretation

This proves the journal writer now preserves strict-replay metadata when the runtime provides it, and that missing fields are surfaced explicitly as null plus blocker labels rather than being invented.

It does not prove the old `.runtime/candidates/candidate_journal.jsonl` artifact is certifiable. That file still needs regeneration from a runtime path that emits explicit feature-cutoff, earliest-entry, and OOS provenance.

