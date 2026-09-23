# Change Manifest

### Modified Files:
- `core/causal_strategy_harness.py`:
  - Defined `StrategyObservation` dataclass.
  - Added `strategy_qualified`, `execution_eligible`, `execution_block_reason`, `feed_age_sec`, `option_quote_age_sec`, `candidate_state`, `qualification_evidence` fields to `CausalCandidate`.
  - Added `observations` and `telemetry_counters` fields to `StrategyEvaluationResult`.
  - Implemented multi-state strategy observation logging and metric accumulation.
- `core/kite_read_only_observation_runtime.py`:
  - Added emission of `strategy_observations.jsonl` and `executable_pool.jsonl`.
  - Added structured `PIPELINE_TELEMETRY` log reporting per observation pulse.

### Added Files:
- `tests/test_candidate_pipeline_architecture_repair.py`:
  - 10 comprehensive behavioral test cases verifying all architecture requirements.
