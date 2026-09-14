# Statistical Research Certification v1

## Scope

Offline research validation only. This layer does not modify strategies, thresholds, execution, broker adapters, risk controls, feeds, credentials, dashboards, or LIVE/PAPER/SIM behavior.

Safety contract:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
```

`CERTIFIED_RESEARCH` is not authorization to trade. It means only that the supplied research evidence passed the configured offline gates.

## Why this exists

A positive backtest or positive WFA is not sufficient evidence of an edge. Strategy research is exposed to temporal overfit, repeated-search selection bias, parameter fragility, small-sample uncertainty, false discoveries, unrealistic costs, and holdout contamination.

The validation stack therefore keeps distinct questions separate:

1. **Experiment lineage** — was the search history retained rather than winner-only reporting?
2. **Parameter stability** — is the result a stable region rather than a numerical peak?
3. **WFA** — does repeated chronological train/validate behavior generalize through time?
4. **CSCV/PBO** — how often does the in-sample winner rank poorly out of sample?
5. **PSR / MinTRL / power** — is the observed Sharpe statistically distinguishable with enough evidence?
6. **DSR / FWER-style selection correction** — is the selected winner still impressive after accounting for the search that produced it?
7. **FDR control** — when accepting multiple discoveries, control the expected false-discovery proportion rather than treating each p-value independently.
8. **Cost robustness** — does the strategy survive the governed execution-cost model?
9. **Inference-model validity** — do distributional/serial-dependence assumptions permit the claimed inference?
10. **Locked holdout** — does a frozen candidate survive one-shot untouched chronological data?
11. **Prospective confirmation** — optional for historical research certification; required when the governing campaign says so.

## Implemented primitives

`core/research_validation/statistics.py` provides:

- per-period sample Sharpe;
- probabilistic Sharpe ratio with skew/kurtosis adjustment and conservative serial-dependence effective sample size;
- minimum track-record length approximation;
- entropy/eigenvalue effective rank for correlated trial families;
- deflated Sharpe ratio against an expected searched maximum;
- Bonferroni FWER decisions;
- Benjamini-Hochberg FDR decisions;
- CSCV probability of backtest overfitting.

`core/research_validation/policy.py` provides a fail-closed evidence gate. Missing/invalid evidence cannot certify. Low power and insufficient track record are `INCONCLUSIVE`, not falsely converted into evidence against the hypothesis.

## Required experiment accounting

All meaningful strategy searches must retain rejected trials in the existing research registry. Effective trial count is a statistical correction for correlated variants; it is not permission to omit raw experiments.

At minimum preserve:

```text
hypothesis_id
experiment_id
version_id
timestamp
data / market universe
parameter set
reason for experiment
branch
commit SHA
result / rejection state
statistical evidence references
```

If declared search count and registered search count disagree, certification is blocked with `SEARCH_HISTORY_INCOMPLETE`.

## Gate interpretation

Hard failures include parameter fragility, WFA failure, excessive PBO, PSR/DSR below policy, cost-robustness failure, failed holdout, and any explicitly required additional gate.

Evidence deficiencies produce either:

- `BLOCKED` when evidence is missing, malformed, hidden, or inference assumptions are invalid; or
- `INCONCLUSIVE` when the evidence is valid but underpowered/too short.

This distinction is deliberate. A small sample is not proof that a strategy fails.

## Default policy thresholds

The v1 code ships with explicit defaults rather than pretending there is one universal economic truth:

```text
max_pbo = 0.20
min_psr = 0.95
min_dsr = 0.95
min_power = 0.80
```

These are policy defaults, not strategy thresholds. Future changes must be separately justified and tested; they must not be silently tuned to rescue a candidate.

## Adversarial test plan

The tests attack:

- NaN/Inf propagation;
- zero-variance returns;
- tiny samples;
- non-square/asymmetric/non-PSD correlation matrices;
- hidden/mismatched experiment counts;
- invalid probabilities and thresholds;
- low power and insufficient track record;
- serial dependence confidence inflation;
- search-size inflation in DSR;
- known FWER/FDR decision examples;
- CSCV selection instability;
- property-level BH monotonicity and effective-rank identity behavior;
- accidental execution authority in a positive certification verdict.

No test may weaken a gate to pass CI.

## Known boundaries

This PR intentionally does **not** claim to implement every 2026 heavy-tail/GARCH inference result. The policy exposes `inference_model_valid`; campaigns with volatility clustering or tail regimes outside the implemented asymptotics must fail closed until an appropriate governed estimator is supplied.

Likewise, PBO is only meaningful when the strategy-return matrix represents the actual candidate family and chronological sample used in the search. A fabricated subset gives fabricated confidence.

## Acceptance proof required before merge

1. Focused research-validation tests pass.
2. Existing repository CI/regression gates do not regress.
3. No broker/order/live/risk/strategy imports are introduced by `core/research_validation`.
4. PR diff contains only research-validation code, tests, and documentation.
5. Exact head SHA is recorded after CI.
6. Failed CI must be investigated, not bypassed.
