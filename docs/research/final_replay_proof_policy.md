# Final replay proof policy

## Verdict

`PARTIAL_REPLAY_CONTEXT_READY`

The replay proof chain can close some remaining metadata blockers by using explicit replay policy or a real joined feed-truth artifact. It cannot honestly close candidate emission by metadata alone.

## What the current runner and bundle recorder do

The replay candidate handoff runner currently:

- reads a real replay row from JSONL
- builds a normalized snapshot
- builds `StrategyContext`
- runs the strategy/ranking path
- writes isolated replay-context evidence

The bundle recorder currently:

- merges the raw replay row, normalized snapshot, strategy context, and ranking report
- builds a replay context record
- fails closed when required timing/OOS/feed-truth fields are missing

The important point is that the current code preserves evidence, but it does not invent missing runtime truth.

## Policy for the remaining blockers

### 1. `feature_cutoff_ts`

Source policy:

- Prefer an explicit replay-row field when present.
- If the replay row does not carry it, allow an explicit replay-run argument/config field that states the snapshot feature cutoff for the proof slice.
- Do not infer it from `created_at`, `signal_ts`, or candidate creation time.

Fail-closed behavior:

- If neither the replay row nor the explicit replay-run policy provides it, the runner must persist `feature_cutoff_ts = null` and record `missing_feature_cutoff_ts`.

Honest classification:

- `REQUIRES_EXPLICIT_REPLAY_POLICY`

### 2. `earliest_entry_ts`

Source policy:

- Prefer an explicit replay-row field when present.
- If the replay slice is tied to a real execution-policy artifact, that artifact may provide the earliest eligible entry time.
- Do not infer same-event entry from the replay row, signal time, or candidate creation time.

Fail-closed behavior:

- If no explicit execution-policy source exists, persist `earliest_entry_ts = null` and record `missing_earliest_entry_ts`.

Honest classification:

- `REQUIRES_EXPLICIT_REPLAY_POLICY`

### 3. `feed_truth_state`

Source policy:

- Only accept this from a real feed-truth artifact or a replay row that already carries an explicit feed-truth join result.
- Do not mark the feed healthy from the presence of a quote row alone.

Fail-closed behavior:

- If no feed-truth artifact is available, persist `feed_truth_state = null` and record `missing_feed_truth_state`.

Honest classification:

- `REQUIRES_RUNTIME_FEED_TRUTH_ARTIFACT`

### 4. `feed_truth_reason_code`

Source policy:

- Same source constraint as `feed_truth_state`.
- The reason code must come from the same real feed-truth artifact or explicit join result.

Fail-closed behavior:

- If no feed-truth artifact is available, persist `feed_truth_reason_code = null` and record `miss-ing_feed_truth_reason_code`.

Honest classification:

- `REQUIRES_RUNTIME_FEED_TRUTH_ARTIFACT`

## Natural candidate emission

Candidate emission is not a metadata problem.

If the replay row still does not naturally emit a candidate after the metadata gaps are closed, the proof should treat that as one of two honest outcomes:

1. Scan a broader regenerated replay window that contains more relevant market context and candidate-producing rows.
2. Capture the replay bundle during a real candidate-producing runtime event, using the isolated replay runner only as evidence capture.

Fail-closed behavior:

- Do not synthesize a candidate.
- Do not force ranking acceptance.
- Do not mark the proof complete just because metadata is now present.

Honest classification:

- `NOT_AVAILABLE` until a replay slice naturally produces a candidate or the replay context is shown to be complete enough to do so.

## Recommended proof path

1. Keep the replay bundle recorder strict.
2. Add only explicit replay policy for:
   - `feature_cutoff_ts`
   - `earliest_entry_ts` only when backed by a real execution-policy artifact
3. Join a real feed-truth artifact for:
   - `feed_truth_state`
   - `feed_truth_reason_code`
4. Re-scan a broader replay window.
5. If candidate emission still does not occur naturally, stop and classify the slice honestly instead of inventing a trade.

## Implementation note

The replay runner now accepts explicit policy inputs for:

- `feature_cutoff_ts`
- `earliest_entry_ts`
- `feed_truth_state`
- `feed_truth_reason_code`
- `feed_truth_source`

These inputs are fail-closed when partial or inconsistent. They only close metadata gaps; they do not create candidate evidence.

## Final conclusion

Metadata blockers can be closed by explicit replay policy and a real feed-truth artifact.

Candidate emission requires broader or more relevant replay context. It is not solved by metadata preservation alone.
