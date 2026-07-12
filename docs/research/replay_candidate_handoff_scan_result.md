# Replay candidate handoff scan result

Date: 2026-07-12

## Scope

I scanned a bounded slice of real replay events through the isolated replay-only candidate handoff entrypoint:

```bash
python scripts/run_replay_candidate_handoff.py \
  --source <isolated one-row replay slice> \
  --output-root /tmp/replay_candidate_handoff_scan \
  --run-id scan-XXX \
  --strategy-id vwap_reclaim_rejection_v1
```

Each slice was cut from the real replay source `.runtime/market_data/ticks_20260703.jsonl`. No synthetic candidates were created. No production artifacts were overwritten.

## Scan summary

- Events scanned: 5
- First candidate found: none
- Final verdict: `BLOCKED_NO_CANDIDATE_EVENT_FOUND`

## Blocker distribution

- `BLOCKED_NO_NORMALIZED_SNAPSHOT`: 0
- `BLOCKED_NO_STRATEGY_CONTEXT`: 0
- `BLOCKED_NO_CANDIDATE`: 5
- `BLOCKED_RANKING_REJECTED`: 0
- `BLOCKED_NO_PERSISTENCE`: 0

## Per-event evidence

The first five real replay events all reached:

1. normalized snapshot
2. StrategyContext
3. candidate stage blocked with `no_ranked_candidates`

Representative isolated audit artifact:

- `/tmp/replay_candidate_handoff_scan/scan-000/replay_candidate_handoff_audit.json`

Representative evidence from that file:

- replay event id: `1783049403.7002602`
- stage evidence:
  - normalized snapshot: proven
  - StrategyContext: proven
  - candidate: blocked with `no_ranked_candidates`

## Candidate/journal persistence

No candidate reached handoff persistence, so no isolated handoff artifact or candidate journal row was written for the scanned events.

## Interpretation

This scan proves the replay-only entrypoint is wired correctly and fails closed on real replay rows, but the sampled events did not naturally emit a candidate.

The current replay source still needs a broader or different slice if the goal is to find a naturally emitted candidate through the isolated proof runner.

