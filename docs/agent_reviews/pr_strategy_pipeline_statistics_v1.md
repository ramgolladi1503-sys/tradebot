# Deterministic Statistics Pipeline Review

mode: RESEARCH
candidate_id: STRATEGY_PIPELINE_STATISTICS_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Replace permissive evidence parsing and latest-file statistics with exact Outcomes lineage, frozen partitions, deterministic inference, negative controls, walk-forward analysis, untouched holdout gates, and cost sensitivity.
timestamp: 2026-07-22T20:35:00Z
is_order_action: false
broker_api_called: false
source: agent/strategy-pipeline-statistics-v1

## Agent Work Contract

Implement only the Statistics-stage repair above draft PRs #700 through #703. Statistics must consume exactly one signed Outcomes result manifest plus one caller-declared validation-config JSON. It must trace the same run through Outcomes, Truth, Registry, and Research, recover the frozen development and holdout windows, verify the original candidate file hash, reconcile gross PnL minus costs to net PnL, and evaluate every mandatory gate deterministically.

## Scope Guard

In scope: strict Statistics adapter, deterministic metrics and random seeds, candidate partition/date validation, frozen-window enforcement, minimum sample gates, net expectancy, profit factor, max drawdown, bootstrap confidence interval, sign-randomization and direction-flip controls, chronological walk-forward folds, cost sensitivity, canonical script routing, signed pass/block artifacts, and focused tests.

Out of scope: signal generation, parameter optimization, market data, broker calls, order actions, live configuration, risk, feeds, dashboards, current legal/fee-rate claims, certification, paper observation, and Drift.

The legacy standalone statistical command remains available outside pipeline mode. Its enum parser is also changed to reject missing/invalid values rather than silently substituting the first enum member.

## Grill Me Review

- Can Statistics choose the newest Outcomes file? No. The signed Outcomes manifest is an automatic upstream input for the exact run.
- Can development and holdout dates be relabeled after replay? No. The candidate file path and SHA-256 are preserved by Outcomes and reverified by Statistics.
- Can holdout rows fall outside the frozen Research window? No. Every session date must lie inside its frozen development or holdout interval, and partition date overlap is rejected.
- Can gross/net PnL inconsistency pass? No. Every complete record must satisfy gross PnL minus recorded total cost equals net PnL.
- Are bootstrap and null tests reproducible? Yes. Iterations, seed, confidence, and null thresholds are explicit hash-pinned configuration.
- Is a positive aggregate enough? No. Development and holdout expectancy/PF, drawdown, bootstrap lower bound, null-control p-value, direction-flip control, walk-forward profitable-fold ratio, and worst cost-sensitivity expectancy all have independent gates.
- Can failed statistics disappear? No. Every failed gate is listed in a hash-verified `statistics.stage.json` attached to the BLOCKED result.

## Hermes Review

The stage is research/paper-only and read-only. It reads signed artifacts and historical evidence, performs deterministic calculations, and writes only run-scoped pipeline artifacts. It imports no broker client, creates no order action, changes no strategy logic, and grants no live authority.

## GSD Review

The old statistical command silently mapped unknown enums to an arbitrary first member and the orchestrator could select the newest evidence file. The repaired pipeline route accepts exact signed Outcomes evidence and a declared validation policy, reconstructs frozen lineage, computes deterministic development/holdout evidence, and emits a single explicit pass/block verdict. No default VALID, STABLE, or HIGH_CONFIDENCE state is fabricated.

## QA / Safety Review

Focused local validation:

- full stacked focused suite -> `49 passed`;
- Python compilation for the Statistics adapter and canonical command -> passed.

Statistics tests prove deterministic repeated output, all-gate success, explicit holdout threshold blocking, hash-verified failed diagnostics, frozen holdout-window rejection, and candidate-file mutation detection after Outcomes. The inherited stack continues to prove Research, Registry, Truth, and Outcomes lineage and safety.

Full repository CI and every parent-stack workflow must pass on immutable heads.

## Acceptance Proof

Acceptance requires all 49 focused tests, Python compilation, direct pipeline command smoke, and all repository workflows to pass. Statistics must block on wrong Outcomes lineage, incomplete causal contract, changed candidate file, invalid partitions or dates, frozen-window violations, development/holdout overlap, no complete records, net-PnL reconciliation failure, insufficient samples, weak expectancy/PF, excessive drawdown, non-positive bootstrap lower bound, failed null controls, unstable WFA, or failed stressed costs.

## Runtime Proof Required After Merge

Run the governed stack through Outcomes with candidate rows containing frozen `sample_partition` and `session_date`. Declare one exact validation-config JSON and execute Statistics. Retain `statistics.stage.json` and `statistics.result.json`. Repeat with one holdout date outside the frozen window and confirm fail-closed rejection. Repeat with a stricter holdout threshold and confirm a hash-verified BLOCKED diagnostic rather than a partial success.

## What This PR Does Not Prove

This PR does not prove future profitability, market-data correctness, perfect fill replication, optimal thresholds, immunity to regime change, certification readiness, paper performance, or live performance. It does not repair Certification or Drift.

## Human Approval

Human review is required before merge. This stacked PR grants no paper or live trading authority, performs no automatic merge or deployment, and cannot call a broker or create an order action.
