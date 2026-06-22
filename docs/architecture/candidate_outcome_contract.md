# Candidate Outcome Contract

The candidate outcome contract enforces rigorous probability semantics on candidate generation.

## Purpose
The bot must define probability as:
"Probability of [event] within [time horizon] under [cost model]."

## Fields
- `candidate_id`
- `strategy_name`
- `created_at`
- `entry_price`
- `target_price`
- `stop_price`
- `prediction_event`: Represents the predicted event. Values include `TARGET_BEFORE_STOP`, `TARGET1_BEFORE_STOP`, `PROFIT_BEFORE_TIME_STOP`, `NO_EXECUTABLE_EVENT`.
- `prediction_horizon_minutes`
- `valid_until`
- `time_stop`
- `cost_model`
- `confidence_score`
- `probability_target_before_stop`
- `calibration_source`
- `execution_ok`
- `candidate_status`
- `is_fallback`, `is_advisory`, `is_stale`, `is_recovered`

This explicit definition separates heuristic scores from true probability.
