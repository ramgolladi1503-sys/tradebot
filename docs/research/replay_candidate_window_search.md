# Replay candidate window search

## Verdict

`BLOCKED_NO_CANDIDATE`

I scanned bounded replay windows from the regenerated replay artifact using the isolated replay candidate handoff runner. No natural candidate was emitted in any scanned window.

## Input artifact

- `/tmp/resolved_option_ticks_20260702_regenerated.parquet`
- extracted replay JSONL windows written under `/tmp/replay_candidate_handoff_window_search/`

## Windows scanned

Candidate-likely anchors were chosen from the regenerated parquet by prioritizing rows with the tightest bid/ask spread and valid quote fields:

- anchor `612731` — `BANKNIFTY CE 57500 2026-07-28`
- anchor `612773` — `BANKNIFTY CE 57500 2026-07-28`
- anchor `612845` — `BANKNIFTY CE 57500 2026-07-28`

For each anchor, these windows were scanned:

- 5 rows
- 20 rows
- 100 rows

That produced 9 isolated replay runs.

## Commands run

Representative command pattern:

```bash
python scripts/run_replay_candidate_handoff.py \
  --source <window-jsonl> \
  --output-root /tmp/replay_candidate_handoff_window_search/out \
  --run-id <window-run-id> \
  --strategy-id vwap_reclaim_rejection_v1 \
  --is-oos false \
  --oos-label IS \
  --oos-source explicit_replay_run_context \
  --partition-id replay-context-proof \
  --split-name in_sample_replay_probe \
  --feature-cutoff-ts <source_timestamp> \
  --earliest-entry-ts <source_timestamp_plus_1s> \
  --feed-truth-state LIVE \
  --feed-truth-reason-code OK \
  --feed-truth-source explicit_replay_policy
```

## Candidate emission

- Candidate emitted: `no`
- First candidate event id: `none`
- Handoff persistence reached: `no`
- Journal persistence reached: `no`

## Blocker distribution

All 9 scanned runs ended with the same blocker:

- `BLOCKED_NO_CANDIDATE`: 9

No runs returned ranking acceptance or candidate persistence.

## Stage coverage

The replay path still proved the earlier stages in each scan:

- normalized snapshot: proven
- strategy context: proven
- replay context bundle recorder: proven
- candidate emission: blocked

## Conclusion

The regenerated replay artifact and explicit policy inputs are sufficient to reach replay-context-ready bundle recording, but they still do not naturally produce a candidate in the scanned windows. The remaining blocker is behavioral, not metadata: the replay slice itself is not candidate-generating.
