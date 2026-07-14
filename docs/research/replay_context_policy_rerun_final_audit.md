# Replay context policy rerun final audit

## Verdict

`REPLAY_CONTEXT_READY_NO_CANDIDATE_FOUND`

This rerun proves that explicit replay policy inputs now propagate into the replay bundle correctly. The bundle is metadata-ready, but this replay slice still does not naturally emit a candidate.

## Replay command used

```bash
python scripts/run_replay_candidate_handoff.py \
  --source /tmp/replay_context_bundle_regenerated_input.jsonl \
  --output-root /tmp/replay_candidate_handoff_policy_rerun \
  --run-id policy-rerun-001 \
  --strategy-id vwap_reclaim_rejection_v1 \
  --is-oos false \
  --oos-label IS \
  --oos-source explicit_replay_run_context \
  --partition-id replay-context-proof \
  --split-name in_sample_replay_probe \
  --feature-cutoff-ts 2026-07-02T10:52:40+05:30 \
  --earliest-entry-ts 2026-07-02T10:52:41+05:30 \
  --feed-truth-state LIVE \
  --feed-truth-reason-code OK \
  --feed-truth-source explicit_replay_policy
```

## Input row used

Source: `/tmp/replay_context_bundle_regenerated_input.jsonl`

Relevant row fields:

- `source_timestamp`: `2026-07-02 10:52:40`
- `option_type`: `CE`
- `strike`: `24050.0`
- `expiry`: `2026-07-07`
- `is_oos`: `false`
- `oos_label`: `IS`
- `oos_source`: `explicit_replay_run_context`

## Stage-by-stage evidence

| stage | proven yes/no | evidence source | object/record id | notes |
|---|---:|---|---|---|
| normalized_snapshot | yes | `replay_context_bundle_regenerated_input.jsonl` | `0` | Real replay input row parsed by runner. |
| strategy_context | yes | `replay_context_bundle_regenerated_input.jsonl` | `0` | Strategy context path reached. |
| bundle_recorder | yes | `/tmp/replay_context_bundles/policy-rerun-001/replay_context_bundle_latest.json` | `0` | Isolated bundle written and metadata-ready. |
| candidate | no | `/tmp/replay_candidate_handoff_policy_rerun/policy-rerun-001/replay_candidate_handoff_audit.json` | `0` | Blocked with `BLOCKED_NO_CANDIDATE`. |

## Blocker comparison

The following blockers are closed in the replay bundle:

- `missing_feature_cutoff_ts`: gone
- `missing_earliest_entry_ts`: gone
- `missing_feed_truth_state`: gone
- `miss-ing_feed_truth_reason_code`: gone
- `missing_feed_truth_source`: gone
- `missing_is_oos`: gone
- `missing_oos_label`: gone
- `missing_oos_source`: gone

Remaining blocker:

- `BLOCKED_NO_CANDIDATE`

## Bundle evidence

The isolated bundle at `/tmp/replay_context_bundles/policy-rerun-001/replay_context_bundle_latest.json` now contains the explicit policy fields and provenance markers:

- `replay_context.feature_cutoff_ts = 2026-07-02T10:52:40+05:30`
- `replay_context.earliest_entry_ts = 2026-07-02T10:52:41+05:30`
- `replay_context.feed_truth_state = LIVE`
- `replay_context.feed_truth_reason_code = OK`
- `replay_context.feed_truth_source = explicit_replay_policy`
- `replay_context.field_sources.feature_cutoff_ts_source = preserved:feature_cutoff_ts`
- `replay_context.field_sources.earliest_entry_ts_source = preserved:earliest_entry_ts`
- `replay_context.field_sources.feed_truth_state_source = preserved:feed_truth_state`
- `replay_context.field_sources.feed_truth_reason_code_source = preserved:feed_truth_reason_code`

Preserved OOS and quote provenance remain present:

- `replay_context.is_oos = false`
- `replay_context.oos_label = IS`
- `replay_context.oos_source = explicit_replay_run_context`
- `replay_context.quote_age_sec = 0`
- `replay_context.quote_source = replay_source:replay_context_bundle_regenerated_input.jsonl`

## Conclusion

The policy propagation bug is fixed. The replay bundle now carries explicit OOS, timing, and feed-truth policy inputs with provenance markers. The remaining blocker is behavioral: this replay slice still does not naturally emit a candidate, so replay-context readiness is now proven, but candidate generation is not.
