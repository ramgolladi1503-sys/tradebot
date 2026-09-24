# Candidate Pool Semantics & State Machine

| Pipeline Stage | State / Reason Code | Emitted To File | `strategy_qualified` | `execution_eligible` |
|---|---|---|---|---|
| Inapplicable Asset | `STRATEGY_INAPPLICABLE` | `strategy_observations.jsonl` | False | False |
| Missing Prerequisites | `PREREQUISITE_MISSING` | `strategy_observations.jsonl` | False | False |
| Near Signal (0.50 <= conf < 0.70) | `NO_QUALIFIED_SIGNAL` | `strategy_observations.jsonl` | False | False |
| Live Quote Stale (Live Signal) | `REQUIRED_LIVE_INPUT_STALE` | `strategy_observations.jsonl` | False | False |
| Completed Bar Signal + Stale Quote | `FEED_STALE_EXECUTION_BLOCK` | `candidate_pool.jsonl` | True | False |
| Completed Bar / Live + Fresh Quote | `EXECUTION_ELIGIBLE` | `candidate_pool.jsonl` & `executable_pool.jsonl` | True | True |
