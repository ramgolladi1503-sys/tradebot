# Execution Blockers Taxonomy & Proof

| Reason Code | Category | Trigger Condition | Pipeline Action |
|-------------|----------|-------------------|-----------------|
| FEED_STALE_EXECUTION_BLOCK | Execution | Completed-bar signal valid, but execution quote > 2.5s | Candidate state = QUALIFIED_EXECUTION_BLOCKED |
| REQUIRED_LIVE_INPUT_STALE | Qualification | Strategy needs live tick to qualify, feed > 2.5s | Qualification = UNKNOWN, 0 candidates |
| STRATEGY_INAPPLICABLE | Registry | Symbol not in strategy registry  | Applicability = INAPPLICABLE, 0 candidates |
| PREREQUISITE_MISSING | Data Integrity | Pre-conditions (e.g. prev_day_close, vwap) missing | Qualification = PREREQUISITE_MISSING, 0 candidates |
| NO_QUALIFIED_SIGNAL | Signal Engine | Signal confidence < 0.70 or confidence < 0.50 | Qualification = NO_SIGNAL / NEAR_SIGNAL, 0 candidates |
