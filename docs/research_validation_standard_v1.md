# TradeBot Research Validation Standard V1

## Agent work contract

```text
source_agent=ChatGPT

action=DEFINE_AND_IMPLEMENT_OFFLINE_RESEARCH_VALIDATION

title=Research Validation Standard V1

scope=Offline statistical validation only. Add search-trial accounting, Sharpe inference,
multiple-testing controls, PBO, distribution diagnostics, and a fail-closed research verdict.

requested_paths=core/research_validation/**, tests/test_research_validation.py,
docs/research_validation_standard_v1.md

allowed_paths=core/research_validation/**, tests/test_research_validation.py,
docs/research_validation_standard_v1.md

forbidden_paths=main.py, run_live.sh, config/**, credentials.py, core/execution*,
core/broker*, core/order*, core/risk*, core/feed*, strategies/**, runtime/live*, logs/broker*, secrets*

expected_tests=tests/test_research_validation.py

acceptance_proof=Reference-number parity for the public 2026 Sharpe examples; effective-trial
behavior; search-space DSR penalty; FWER/FDR corrections; trial-ledger integrity; PBO stable-vs-regime
counterexample; heavy-tail warning behavior; fail-closed verdict with zero live authority.
```

## Purpose

This standard closes a specific research-governance gap: a positive historical backtest or positive
walk-forward result is not sufficient evidence that a strategy is real. Strategy discovery is a search
process. The search itself creates selection bias, multiple-testing risk, and false discoveries.

This layer complements the existing TradeBot WFA implementation. It does not replace WFA and does
not change strategy logic, live execution, broker behavior, risk limits, feeds, or order authority.

## Required research sequence

1. Observe a market phenomenon.
2. State a falsifiable mechanism/hypothesis before optimizing against P&L.
3. Register every meaningful strategy/parameter trial in a complete experiment ledger.
4. Run the development backtest using point-in-time information and a declared cost model.
5. Test parameter-neighborhood stability rather than selecting an isolated optimum.
6. Run chronological WFA and retain stitched OOS returns.
7. When a family of candidate strategies was searched, estimate Probability of Backtest Overfitting
   with CSCV/PBO where the data shape makes that test appropriate.
8. Measure Sharpe uncertainty with skewness, non-excess kurtosis, and serial-correlation adjustment.
9. Require Probabilistic Sharpe Ratio, Minimum Track Record Length, and statistical power evidence.
10. Preserve the raw number of experiments and estimate effective independent trials from the
    candidate-return correlation structure. Effective trials never replace the raw search ledger.
11. Correct search-and-select claims with Deflated Sharpe Ratio / FWER-style controls. For a set of
    discoveries, report an appropriate FDR procedure rather than pretending FWER and FDR are the same.
12. Diagnose return distributions before relying on Gaussian-style Sharpe asymptotics. Sample
    kurtosis is a warning signal only; a finite sample cannot prove that population fourth moments exist.
13. Freeze the champion before a final chronological holdout. Do not repair the strategy after seeing
    that holdout and still call the same holdout untouched.
14. Require prospective confirmation before any research-evidence pass.
15. A research-evidence pass never grants live execution authority.

## What each gate answers

| Gate | Question |
| --- | --- |
| WFA | Does the development/selection procedure generalize repeatedly through chronological OOS windows? |
| PBO/CSCV | How often does an in-sample winner become mediocre or worse out of sample? |
| PSR | How probable is the observed Sharpe to exceed the benchmark after sampling uncertainty? |
| MinTRL | How much track record is required before the Sharpe claim reaches the target significance? |
| Power | Was the experiment capable of detecting the alternative edge if it existed? |
| Effective trials | How many economically/statistically distinct searches were represented by correlated candidates? |
| DSR/FWER | Is the selected champion still exceptional after accounting for the search that produced it? |
| FDR | Among a set of accepted discoveries, how aggressively must significance be controlled to limit false discoveries? |
| Holdout | Does the frozen champion survive data never used in development or repair? |
| Prospective | Does the edge continue after the research decision is frozen? |

## Raw trials versus effective trials

Both must be reported.

Example:

```text
RAW_TRIALS=20000
EFFECTIVE_TRIALS=73.4
```

`RAW_TRIALS` describes what was actually searched. `EFFECTIVE_TRIALS` is a statistical estimate of how
many independent dimensions that correlated search represents. A low effective-trial count is never
permission to delete or hide failed experiments.

If the candidate-return history needed to estimate effective trials is missing, the correct state is
`EFFECTIVE_TRIAL_COUNT_MISSING`, not an invented count.

## Year-specific strategy research

Do not optimize until a particular calendar year becomes profitable.

Allowed use of a year:

```text
2023 differs from adjacent periods
-> measure volatility / trend / breadth / dispersion / gap behavior / liquidity
-> propose a mechanism
-> locate the same market state throughout the full corpus
-> test the frozen mechanism across all comparable occurrences
```

Disallowed interpretation:

```text
2023 was weak
-> keep modifying indicators/stops/targets until 2023 turns positive
-> call the repaired rule a discovery
```

A year is an observation/regime laboratory, not a target label for fitting.

## Implemented V1 primitives

`core/research_validation/statistics.py`

- generalized Sharpe-ratio variance with skewness, kurtosis, and lag-1 autocorrelation
- Probabilistic Sharpe Ratio
- Minimum Track Record Length
- critical Sharpe and test power
- effective rank and effective-trial estimation from candidate returns
- expected maximum Sharpe and Deflated Sharpe Ratio
- Bonferroni, Sidak, and Holm FWER adjustments
- Benjamini-Hochberg and Benjamini-Yekutieli FDR adjustments

`core/research_validation/pbo.py`

- bounded CSCV PBO estimator using candidate-strategy return columns
- no broker, order, or runtime dependencies

`core/research_validation/ledger.py`

- immutable trial records
- mandatory trial/hypothesis/strategy/code/data identities
- parent-trial lineage checks
- deterministic ledger SHA-256

`core/research_validation/distribution.py`

- descriptive mean/std/skew/kurtosis/lag-1 correlation
- heavy-tail warning state
- explicit refusal to infer population moment existence from one finite historical sample

`core/research_validation/verdict.py`

- fail-closed gate composition
- distinguishes missing evidence from negative evidence
- requires WFA, cost robustness, holdout, and prospective confirmation by default
- a pass remains read-only and never authorizes live execution

## Default research verdict blockers

The evaluator can emit, among others:

```text
SEARCH_HISTORY_INCOMPLETE
INFERENCE_MODEL_INVALID
MINIMUM_TRACK_RECORD_MISSING
UNDERPOWERED_TRACK_RECORD
POWER_MISSING
UNDERPOWERED
PSR_MISSING
PSR_FAIL
EFFECTIVE_TRIAL_COUNT_MISSING
SEARCH_ADJUSTMENT_MISSING
DSR_FAIL
PBO_HIGH
WFA_FAIL
WFA_NOT_PROVEN
COST_ROBUSTNESS_FAIL
COST_ROBUSTNESS_UNKNOWN
HOLDOUT_FAIL
HOLDOUT_NOT_RUN
PROSPECTIVE_FAIL
PROSPECTIVE_NOT_CONFIRMED
RESEARCH_EVIDENCE_PASS
```

`RESEARCH_EVIDENCE_PASS` is deliberately not named `CERTIFIED_FOR_LIVE`.

## Safety invariants

Every verdict preserves:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
```

V1 is not wired into live or paper execution.

## Method references used for V1

The implementation is independently written from the published methods and checked against public
reference numbers where available.

- David H. Bailey, Jonathan Borwein, Marcos Lopez de Prado, Qiji Jim Zhu: *The Probability of Backtest Overfitting*.
- David H. Bailey and Marcos Lopez de Prado: *The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality*.
- Marcos Lopez de Prado et al.: public 2025/2026 Sharpe-ratio inference reference implementation and associated paper material covering generalized Sharpe variance, PSR, MinTRL, power, effective trials, FWER and FDR.
- Yoav Benjamini and Yosef Hochberg: false discovery rate control.
- Yoav Benjamini and Daniel Yekutieli: FDR control under dependence.

## V1 limitations

1. V1 does not automatically decide that a population fourth moment exists. Heavy-tail warnings require
   a separate validated inference choice before `inference_model_valid=true` should be supplied.
2. Effective-rank trial estimation is implemented. Clustering and random-matrix/Marchenko-Pastur
   estimators remain future independent cross-checks; they must not be fabricated as already present.
3. V1 provides batch FDR adjustments. It does not claim a sequential-FDR implementation.
4. PBO requires a coherent matrix of comparable candidate returns. It should not be computed from
   unrelated strategies with incompatible observation timestamps merely to produce a number.
5. The module is not yet wired into every historical strategy-research script. That integration should
   be a separate, reviewable PR after the primitives and contracts are accepted.
