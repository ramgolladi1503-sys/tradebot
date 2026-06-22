# Probability Semantics in Strategy Research

When developing new strategies or tuning existing ones, it is critical to distinguish between heuristic confidence and calibrated probability. The trading engine now enforces strict semantics around how probabilities are constructed and presented to the user.

## The Problem with "Confidence Scores"

Historically, strategies emitted a `confidence_score` (0.0 to 1.0). If a strategy emitted a score of 0.67, the UI would display "67%". This is misleading. What does 67% mean?
- 67% chance of hitting a target before a stop?
- 67% chance of closing green at the end of the day?
- 67% percentile rank among all setups?

Without defining the event and the time horizon, a percentage is just a "confidence-looking number." It is not a probability.

## The Candidate Outcome Contract

To solve this, every strategy should define a `CandidateOutcomeContract` for its candidates.

### Heuristic Confidence (Setup Score)
If your strategy only has a heuristic ranking model (e.g., scoring confluence factors), do not attempt to present it as a probability.
Omit the prediction event and horizon. The UI will honestly display your score as a `Setup score`.

```python
outcome = CandidateOutcomeContract(
    confidence_score=0.67,
    # No event or horizon defined
)
```

### Calibrated Probability (Target-Hit Probability)
If your strategy has a backtested or live-calibrated probability model, you must explicitly define the outcome it predicts.

```python
outcome = CandidateOutcomeContract(
    confidence_score=0.67,
    prediction_event="TARGET_BEFORE_STOP",
    prediction_horizon_minutes=30,
    time_stop="15:15",
    target_price=124.0,
    stop_price=106.0,
    cost_model="realistic_nfo",
    probability_target_before_stop=0.67,
    calibration_source="paper",
)
```

By providing `prediction_event`, `prediction_horizon_minutes`, and `calibration_source`, the UI will legitimately display:
`Target-hit probability within 30 min`

## Strict Rules
- **No horizon = no probability label.** Generic chance percentages without a time window are forbidden.
- **No calibration = confidence score only.** Do not relabel a heuristic score as a probability if it hasn't been rigorously calibrated.
- **Execution Gates are Separate.** Providing a high probability outcome contract does not bypass liquidity, freshness, or safety gates. A 99% probability candidate with stale quotes will still be blocked from execution.
