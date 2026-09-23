# Source Code Audit: Candidate Pipeline Architecture Repair V1

## Architectural Problem
Prior implementation conflated Strategy Qualification with Execution Eligibility in the candidate pool emission logic. Specifically:
1. Signal evaluation checks (Hop 5-8) rejected or suppressed valid causal opportunity signals if quotes were temporarily older than 2.5s.
2. The candidate pool (`candidate_pool.jsonl`) was empty during market conditions where signals qualified from historical/completed bars, blinding downstream auditability and shadow decision tracking.
3. Lack of structured telemetry counters made it impossible to diagnose whether opportunities failed due to:
   - Inapplicable strategy
   - Missing prerequisites
   - Sub-threshold / near-signals
   - Feed staleness at signal generation vs execution time

## Concrete Architecture Fixes
1. **Explicit Separation**:
   - `strategy_observations.jsonl`: Emitted on every evaluation pulse for all canonical strategies, recording applicability state (`APPLICABLE`, `INAPPLICABLE`, `DISABLED`) and qualification state (`QUALIFIED`, `NO_SIGNAL`, `NEAR_SIGNAL`, `UNKNOWN`, `PREREQUISITE_MISSING`).
   - `candidate_pool.jsonl`: Emits all strategy-qualified causal candidates. Signals generated from completed bars enter the candidate pool with `strategy_qualified=True`. If current execution quote is stale, `execution_eligible=False` and `execution_block_reason="FEED_STALE_EXECUTION_BLOCK"`.
   - `executable_pool.jsonl`: Emits strictly candidates passing both strategy qualification and live execution gates (`feed_age <= 2.5s`).
2. **Telemetry Invariant**:
   - Structured dictionary `telemetry_counters` emitted per cycle and aggregated in `PIPELINE_TELEMETRY` log lines.
