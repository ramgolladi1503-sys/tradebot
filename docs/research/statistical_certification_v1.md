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

`CERTIFIED_RESEARCH` is not authorization to trade. It means only that the supplied research evidence passed the locked v1 offline gates.

## Validation questions

The stack keeps separate questions separate:

1. Was the full search history retained rather than winner-only reporting?
2. Is the result a stable parameter region rather than a numerical peak?
3. Does repeated chronological WFA generalize through time?
4. Under CSCV, how often does the IS winner rank below the OOS median?
5. Is Sharpe evidence statistically distinguishable under the implemented inference assumptions?
6. Is the sample long/powered enough to decide at all?
7. Does DSR survive the search that produced the winner?
8. If multiple discoveries are accepted, is FWER/FDR handled explicitly?
9. Does the edge survive the governed execution-cost model?
10. Are the inference assumptions defensible for these returns?
11. Did a frozen candidate survive the untouched holdout without repair?
12. Does prospective evidence confirm the historical result when required?
13. Can the experiment lineage be proven unchanged since it was frozen?
14. Can any caller weaken certification thresholds at runtime?
15. Can malformed Python values (`True`, truthy strings, NaN/Inf) bypass a gate?

## Implemented primitives

`core/research_validation/statistics.py` provides:

- per-period sample Sharpe;
- published non-normal PSR formula using sample length, skewness, and kurtosis;
- minimum track-record length approximation;
- entropy/eigenvalue effective rank for correlated trial families;
- Bailey–López de Prado DSR using the published searched-maximum threshold form;
- Bonferroni FWER decisions;
- Benjamini-Hochberg FDR decisions;
- CSCV/PBO across **all** `S choose S/2` symmetric train/test combinations.

The v1 implementation intentionally does **not** invent a serial-correlation adjustment inside PSR/DSR. If serial dependence, volatility clustering, or tail behavior invalidates the implemented asymptotics, `inference_model_valid` must be false and certification is blocked until a separately verified estimator is available.

## Search-accounting and lineage authority

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

Certification derives the registered experiment count from the registry rather than trusting a caller-supplied count. A declared-vs-registered mismatch blocks with `SEARCH_HISTORY_INCOMPLETE`.

Because the existing frozen dataclasses contain nested mutable lists/dicts, v1 also computes a canonical SHA-256 digest over the complete experiment lineage. Registry-bound certification requires the previously frozen digest. Missing or changed lineage blocks with `LINEAGE_DIGEST_REQUIRED` / `LINEAGE_DIGEST_MISMATCH`.

## Locked certification policy

The v1 policy is identified as:

```text
RESEARCH_CERT_V1
```

and locks:

```text
max_pbo = 0.20
min_psr = 0.95
min_dsr = 0.95
min_power = 0.80
```

A caller cannot pass weaker thresholds to rescue a candidate. Any override blocks with `POLICY_THRESHOLD_OVERRIDE_FORBIDDEN`. A future policy revision must use a new reviewed policy version rather than silently changing v1.

## Gate interpretation

Hard failures include parameter fragility, WFA failure, excessive PBO, PSR/DSR below policy, cost-robustness failure, failed holdout, and required additional-gate failures.

Evidence deficiencies produce either:

- `BLOCKED` when evidence is missing, malformed, hidden, tampered, or inference assumptions are invalid; or
- `INCONCLUSIVE` when valid evidence exists but is underpowered/too short.

A small sample is not evidence that a strategy fails.

## Source-conformance repairs found by hostile review

The hostile review found and corrected two material mathematical deviations before merge:

1. The initial DSR implementation added the mean trial Sharpe to the selection threshold. The published threshold uses the cross-trial Sharpe standard deviation multiplied by the expected maximum standardized-normal term; the extra mean shift was removed.
2. The initial CSCV implementation evaluated only one member of each complementary train/test pair. Published CSCV uses every `S choose S/2` combination; v1 now enumerates all combinations and asserts the expected count.

These are pinned by source-conformance regression tests so they cannot silently return.

## Adversarial coverage

Tests and the mutation campaign attack:

- NaN/Inf propagation and zero variance;
- boolean-as-number and truthy-string coercion;
- invalid policy-threshold overrides;
- invalid holdout/prospective enums;
- tiny/underpowered samples;
- non-square/asymmetric/non-PSD correlation matrices;
- hidden/mismatched experiment counts;
- nested lineage mutation after freeze;
- provenance gaps and non-monotonic version history;
- invalid p-values / alpha / q;
- invalid effective-trial counts;
- search-size inflation in DSR;
- incomplete CSCV enumeration;
- undefined strategy statistics inside CSCV;
- known FWER/FDR decision examples;
- accidental execution authority in a positive research verdict.

No test may weaken a gate to pass CI.

## Known boundaries

This PR does **not** claim to implement the complete 2026 GARCH/heavy-tail/generalized Sharpe framework. Those methods require a separate source-conformance implementation and validation campaign. Until then, campaigns whose returns violate the v1 inference assumptions must remain blocked.

PBO is only meaningful when the return matrix contains the actual candidate family and chronological sample used in the search. Hiding trials biases relative ranks and invalidates the claim.

## Acceptance proof required before merge

1. Focused research-validation tests pass.
2. Source-conformance tests pass.
3. Mutation campaign detects every required mutation.
4. Existing repository CI/regression gates do not regress.
5. No broker/order/live/risk/strategy imports are introduced.
6. PR diff remains limited to research-validation code, tests, tools, and documentation.
7. Exact head SHA is recorded after CI.
8. Failed CI is investigated, never bypassed.
