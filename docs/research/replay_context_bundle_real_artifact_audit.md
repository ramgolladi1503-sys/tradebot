# Replay context bundle real artifact audit

## Verdict

`BLOCKED_NO_CANDIDATE`

The isolated replay candidate handoff runner successfully consumed a real runtime replay row derived from the existing runtime parquet artifact and wrote an isolated replay context bundle. It still did not naturally emit a candidate.

This is a blocker inventory, not candidate proof.

## Real input used

- Source artifact: `/Users/madhuram/tradebot-replay-context-proof/runtime/strategy_validation/resolved_option_ticks_20260702.parquet`
- Derived isolated replay input: `/tmp/replay_context_bundle_real_artifact_input.jsonl`

The replay JSONL input was created by extracting one real row from the parquet artifact and writing that row as-is into an isolated temp file. No candidate objects were synthesized.

## Replay command used

```bash
python scripts/run_replay_candidate_handoff.py \
  --source /tmp/replay_context_bundle_real_artifact_input.jsonl \
  --output-root /tmp/replay_candidate_handoff \
  --run-id replay-bundle-audit-001 \
  --strategy-id vwap_reclaim_rejection_v1
```

## Bundle output

- Bundle root: `/tmp/replay_context_bundles/replay-bundle-audit-001/`
- Bundle artifact: `/tmp/replay_context_bundles/replay-bundle-audit-001/replay_context_bundle_0.json`
- Latest bundle artifact: `/tmp/replay_context_bundles/replay-bundle-audit-001/replay_context_bundle_latest.json`

## Stage-by-stage evidence

| Stage | Proven | Evidence source | Object / record id | Notes |
|---|---:|---|---|---|
| Replay input | yes | `/tmp/replay_context_bundle_real_artifact_input.jsonl` | `0` | Real row extracted from runtime parquet artifact. |
| Normalized snapshot | yes | isolated runner output | `0` | Snapshot built from the real replay row. |
| StrategyContext | yes | isolated runner output | `0` | Context created from the normalized snapshot. |
| Strategy | no | isolated runner output | `0` | Strategy path executed, but produced no ranked candidate. |
| Candidate emitted | no | isolated runner output | `0` | `BLOCKED_NO_CANDIDATE`. |
| Ranking | no | isolated runner output | `0` | Ranking was reached, but no ranked candidate existed to accept. |
| Replay context bundle recorder | yes | `/tmp/replay_context_bundles/replay-bundle-audit-001/replay_context_bundle_latest.json` | `evt-001` | Bundle recorder wrote isolated replay-context evidence. |
| Handoff persistence | no | isolated runner output | `0` | No handoff artifact was written because candidate emission failed. |
| Journal persistence | no | isolated runner output | `0` | No journal row was written because candidate emission failed. |

## Replay bundle evidence

- `replay_bundle_id`: `evt-001`
- `replay_event_id`: `0`
- `source_path`: `/tmp/replay_context_bundle_real_artifact_input.jsonl`
- `bundle_ready`: `false`
- `candidate_naturally_emitted`: `no`
- `handoff_reached`: `no`
- `journal_reached`: `no`

## Exact blockers

Bundle readiness blockers:

- `missing_earliest_entry_ts`
- `missing_expiry`
- `missing_feature_cutoff_ts`
- `missing_feed_truth_reason_code`
- `missing_feed_truth_state`
- `missing_is_oos`
- `missing_oos_label`
- `missing_option_type`
- `missing_quote_age_sec`
- `missing_quote_source`
- `missing_strike`
- `missing_source_timestamp`

Runner blocker:

- `BLOCKED_NO_CANDIDATE`

## What this proves

- A real runtime artifact exists in this worktree: `runtime/strategy_validation/resolved_option_ticks_20260702.parquet`
- The replay runner can consume an extracted real row from that artifact.
- The runner can build:
  - normalized snapshot
  - `StrategyContext`
  - isolated replay-context bundle
- The runner still cannot naturally emit a candidate from this row.

## What it does not prove

- It does not prove natural candidate emission.
- It does not prove handoff persistence.
- It does not prove candidate journal persistence.
- It does not prove the real runtime parquet contains enough context to regenerate the persisted candidate chain without additional recorded fields.

## Conclusion

The replay-context bundle recorder is operating on a real runtime artifact, but the available replay row is still too thin to regenerate a candidate naturally.
