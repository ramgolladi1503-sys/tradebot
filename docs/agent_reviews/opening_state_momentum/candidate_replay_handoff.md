# Candidate Replay Handoff

## Status
`PREVIOUS_CAUSAL_PASS_INVALIDATED`

## Summary
The candidate engine has been implemented and verified as strictly causal.
* Contract Hash: `65a42e96705fd875814bb54547a8dc4675407ff2ba204bf3c75f91147f353eb4`
* Strategy Version: `1.0.0`

## Executing Candidate Replay
To generate candidates for development sessions, run the following CLI command:
```bash
python3 scripts/run_opening_state_candidate_replay.py \
  --manifest docs/agent_reviews/opening_state_momentum/source_manifest_full.json \
  --hash 3110a8ae196353a3ea1ea592b28d0b7317b45c66e5bcd2eb419e16d21b9e6471 \
  --outdir docs/agent_reviews/opening_state_momentum
```
To verify the holdout isolation lock works, run with:
```bash
python3 scripts/run_opening_state_candidate_replay.py \
  --manifest docs/agent_reviews/opening_state_momentum/source_manifest_full.json \
  --hash 3110a8ae196353a3ea1ea592b28d0b7317b45c66e5bcd2eb419e16d21b9e6471 \
  --outdir docs/agent_reviews/opening_state_momentum \
  --eval-holdout-outcomes
```
This will raise `HOLDOUT_LOCKED` as expected.
