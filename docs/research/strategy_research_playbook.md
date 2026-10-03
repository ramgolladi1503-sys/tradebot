# Strategy Research Playbook

This playbook defines a research review workflow. Completing it does not certify an edge, grant paper/live readiness, or authorize capital allocation.

## The Prime Directive
**Do not optimize for profit. Optimize for failure.**
Our goal is not to tune parameters until a backtest shows a positive number. Our goal is to attempt to destroy the strategy using mathematically rigorous friction models and lookahead audits. If a strategy survives, it is because its underlying structural edge is too massive to be destroyed.

## Pipeline Execution

Whenever a new strategy or family is proposed, execute the following strict pathway:

### 1. Unified Wrapping
Ensure the strategy logic conforms to the standard `evaluate()` interface. It must accept raw historical dataframes and output explicit `Signal` or `Rejection` dataclasses. No arbitrary print statements; all logic must be measurable.

### 2. Execution of `run_deepdive_pipeline.py`
Run the automated pipeline to aggregate 3 years of mathematical data. This produces:
- `strategy_deepdive_scoreboard.csv`
- `strategy_failure_taxonomy.csv`
- `strategy_regime_matrix.csv`
- `strategy_mfe_mae_matrix.csv`
- `strategy_cost_drag_matrix.csv`

### 3. Forensic Analysis & Regime Selection
Review the `strategy_regime_matrix.csv` only under a registered trial plan that records all inspected regimes, candidate restrictions, selection rules, and the full trial-family denominator.

If outcomes show losses in one or more regimes, preserve the original all-regime candidate and every result. Do not rewrite its gate and describe the filtered result as confirmation. A regime restriction chosen after inspecting outcomes is a **new, outcome-informed, exposed hypothesis** and must be registered as a child trial with the selection rationale and original negative trials retained.

The filtered hypothesis may be evaluated only on a new prospectively collected or otherwise untouched cohort after its exact rule, parameters, costs, stopping policy, and evaluation plan are frozen before access. Previously inspected outcomes remain exposed for both the parent and selected child. Absence of a regime from a report does not remove it from the search denominator.

### 4. Cost Friction Survival
Review the `strategy_cost_drag_matrix.csv`.
The strategy must retain a **Net Expectancy > 0.15R** after the `IndianDerivativesCostModel` applies static Option-Buy spreads and STT penalties. If the gross edge is positive but net edge is negative, the strategy is `REJECTED: Cost/slippage killed`. Do not move it forward.

### 5. Stress Testing
Cost results are reported against the preregistered candidate and all preregistered children. Surviving baseline friction is evidence for further research only; it does not automatically promote a candidate to `READY_FOR_STRESS_TEST` or paper readiness.
Run it through a friction elasticity test (up to `3.00x` synthetic spread). If the net expectancy collapses entirely, it is too fragile for the real market.

### 6. Real Paper Validation
If a strategy survives 3x friction, record that as a bounded synthetic stress result. Any paper-monitor evaluation requires a separate source-authorized, preregistered, human-reviewed release process. Observation counts alone do not prove validity or authorize capital allocation.

## Failure Taxonomy Tracking
Every researched strategy MUST be permanently categorized into one of these buckets. This prevents us from endlessly researching the same flawed concepts.

- **A. Dead signal**: Negative structural expectancy regardless of regime.
- **B. Good signal, bad exit**: High MFE but current exit logic gives it all back.
- **C. Good signal, bad stop**: Strategy frequently reaches 2R but is mathematically ruined by noise wicks.
- **D. Good signal, regime-dependent result**: Outcomes differ by regime. If the restriction was chosen after viewing those outcomes, the restricted rule is a new exposed child hypothesis, not confirmation.
- **E. Too rare to judge**: Insufficient statistical sample size (< 20 trades).
- **F. Cost/slippage killed**: Gross edge exists but is destroyed by option friction.
- **G. Implementation/gating starvation**: The mathematical conditions are so strict the engine starves.
- **H. Research survivor**: Successfully passed all filters and friction tests.
