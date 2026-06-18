# Strategy Research Playbook

This playbook defines the immutable standard operating procedure for the Deep-Dive Pipeline. It guarantees that any candidate strategy progressing towards Live Paper Trading has been subjected to extreme mathematical scrutiny.

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

### 3. Forensic Analysis & Amputation
Review the `strategy_regime_matrix.csv`.
If the strategy has a positive gross expectancy globally, but bleeds heavily in certain regimes (e.g. `TREND_DOWN`), you must explicitly hardcode a gate to **amputate** that regime from the strategy's allowable bounds.
- *Rule*: Never "tune" an indicator to fix a bleeding regime. Ban the regime entirely.

### 4. Cost Friction Survival
Review the `strategy_cost_drag_matrix.csv`.
The strategy must retain a **Net Expectancy > 0.15R** after the `IndianDerivativesCostModel` applies static Option-Buy spreads and STT penalties. If the gross edge is positive but net edge is negative, the strategy is `REJECTED: Cost/slippage killed`. Do not move it forward.

### 5. Stress Testing
If a strategy survives the regime amputation and baseline cost logic, it is promoted to `READY_FOR_STRESS_TEST`.
Run it through a friction elasticity test (up to `3.00x` synthetic spread). If the net expectancy collapses entirely, it is too fragile for the real market.

### 6. Real Paper Validation
If the strategy survives 3x friction, it is promoted to `READY_FOR_REAL_PAPER`.
It is permanently handed over to the zero-order `run_htf_real_paper_monitor.py` daemon, where it must organically accrue 50 live observations before any capital is allocated.

## Failure Taxonomy Tracking
Every researched strategy MUST be permanently categorized into one of these buckets. This prevents us from endlessly researching the same flawed concepts.

- **A. Dead signal**: Negative structural expectancy regardless of regime.
- **B. Good signal, bad exit**: High MFE but current exit logic gives it all back.
- **C. Good signal, bad stop**: Strategy frequently reaches 2R but is mathematically ruined by noise wicks.
- **D. Good signal, wrong regime**: Bleeds in one regime, thrives in another.
- **E. Too rare to judge**: Insufficient statistical sample size (< 20 trades).
- **F. Cost/slippage killed**: Gross edge exists but is destroyed by option friction.
- **G. Implementation/gating starvation**: The mathematical conditions are so strict the engine starves.
- **H. Research survivor**: Successfully passed all filters and friction tests.
