# Pipeline Health Report: MEAN_REVERSION_EXTENSION

**Verdict:** PARTIAL PASS

### Warnings
- 4324 candidates have 'quote evidence shape complete', but lack true 'quote truth' (quotes were mocked from LTP).
- Missing lineage fields detected.

### Conservation Metrics
```json
{
  "feed_snapshots_seen": 369998,
  "option_chain_ready": 4331,
  "raw_setups_detected": 4469,
  "candidates_generated": 4469,
  "candidates_rejected": 4164,
  "candidates_passed_gates": 160,
  "candidates_ranked": 145,
  "advisory_outputs": 15,
  "executable_outputs": 145,
  "silent_drops": 0,
  "invalid_ranked_candidates": 0,
  "real_market_lineage": 0,
  "replay_partial_lineage": 4324,
  "synthetic_lineage": 0,
  "missing_lineage": 145,
  "real_bid_ask": 0,
  "mocked_bid_ask": 4324,
  "missing_bid_ask": 145,
  "quote_evidence_failures": 0
}
```

### Missing Lineage Fields
```json
{
  "missing_fields": {
    "strategy": 145,
    "blockers": 145
  },
  "blocker_classification_proven": true,
  "blocker_outcome_correctness_proven": false
}
```

