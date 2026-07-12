# Replay candidate likely event search

Date: 2026-07-12

## Goal

Find a replay event that naturally emits a candidate through the isolated replay candidate handoff entrypoint.

## Evidence sources searched

- `.runtime/runtime_candidate_handoff_latest.json`
- `.runtime/candidates/candidate_journal.jsonl`
- `.runtime/opportunities/ranked_pipeline_latest.json`
- `.runtime/market_data/ticks_20260701.jsonl`
- `.runtime/market_data/ticks_20260703.jsonl`

## Candidate hints found

Persisted runtime artifacts showed real candidate-like evidence:

- `runtime_candidate_handoff_latest.json`
  - symbol: `NIFTY`
  - top reportable executable trade id:
    - `NIFTY-2026-07-07-24150-PE-mean-reversion-1782975597`
  - top reportable executable: `true`
  - selector outcome: `NO_EXECUTABLE_OPPORTUNITY`

- `candidate_journal.jsonl`
  - `NIFTY-2026-07-07-23250-PE-continuation-1782885952`
  - `NIFTY-2026-07-07-24250-PE-continuation-1782886615`
  - `BANKNIFTY-OPPORTUNITY_VOLATILITY_EXPANSION-20260701-114959`
  - `NIFTY-2026-07-07-23150-PE-continuation-1782887011`
  - `SENSEX-OPPORTUNITY_VOLATILITY_EXPANSION-20260701-115758`

These are real persisted runtime candidates, but the older journal rows do not yet carry the new strict replay metadata fields.

## Replay rows matched

I built bounded one-row replay slices from real market-data JSONL rows near the hinted symbols:

- `ticks_20260703.jsonl`
  - first 5 replay rows were scanned earlier and all blocked at `BLOCKED_NO_CANDIDATE`
- `ticks_20260701.jsonl`
  - selected rows for:
    - `NIFTY2670724250PE`
    - `BANKNIFTY26JUL59400CE`
    - `NIFTY2670723250PE`

Each slice was run through:

```bash
python scripts/run_replay_candidate_handoff.py \
  --source <isolated one-row replay slice> \
  --output-root /tmp/replay_candidate_handoff_candidate_search \
  --run-id slice-<n> \
  --strategy-id vwap_reclaim_rejection_v1
```

## Blocker distribution

Across the bounded replay slices tried here:

- `BLOCKED_NO_NORMALIZED_SNAPSHOT`: 0
- `BLOCKED_NO_STRATEGY_CONTEXT`: 0
- `BLOCKED_NO_CANDIDATE`: 8
- `BLOCKED_RANKING_REJECTED`: 0
- `BLOCKED_NO_PERSISTENCE`: 0

The replay runner reached:

1. normalized snapshot
2. StrategyContext
3. candidate stage blocked with `no_ranked_candidates`

## Whether a candidate was naturally emitted

No.

The isolated replay handoff runner did not naturally emit a candidate for any of the bounded replay slices tried here.

## Exact missing bridge

The missing bridge is not the journal writer or the handoff writer. Those are already working on existing runtime artifacts.

What is missing is a replay input row or replay slice that reproduces the same upstream runtime context required by the strategy generators to emit a candidate naturally.

In practice, the current replay rows are only option-market ticks, while the persisted candidate artifacts are the result of a richer runtime context that already passed through live/orchestrated market-state, option-pressure, feed-health, and candidate-pool logic.

So the gap is:

`persisted candidate artifact` does not yet map back to a replay slice with the same contextual inputs needed to regenerate a candidate without inventing any intermediate state.

## Commands run

```bash
python - <<'PY'
...
PY

python scripts/run_replay_candidate_handoff.py --source /tmp/one_tick_replay.jsonl --output-root /tmp/replay_candidate_handoff_demo --run-id demo --strategy-id vwap_reclaim_rejection_v1

python scripts/run_replay_candidate_handoff.py --source /tmp/replay_candidate_handoff_candidate_search/slice_0.jsonl --output-root /tmp/replay_candidate_handoff_candidate_search --run-id slice-0 --strategy-id vwap_reclaim_rejection_v1
python scripts/run_replay_candidate_handoff.py --source /tmp/replay_candidate_handoff_candidate_search/slice_1.jsonl --output-root /tmp/replay_candidate_handoff_candidate_search --run-id slice-1 --strategy-id vwap_reclaim_rejection_v1
python scripts/run_replay_candidate_handoff.py --source /tmp/replay_candidate_handoff_candidate_search/slice_2.jsonl --output-root /tmp/replay_candidate_handoff_candidate_search --run-id slice-2 --strategy-id vwap_reclaim_rejection_v1
```

## Conclusion

`BLOCKED_NO_CANDIDATE_EVENT_FOUND`

The repo contains real persisted candidate artifacts, but the available replay rows I sampled do not yet recreate the candidate naturally through the isolated replay handoff entrypoint.

