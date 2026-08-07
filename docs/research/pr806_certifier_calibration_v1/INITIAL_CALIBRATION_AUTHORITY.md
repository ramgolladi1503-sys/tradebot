# PR #806 Certifier Calibration — Initial Authority

## Scope

This is a **reverse-certification of the frozen PR #806 certifier**, not another strategy search and not an attempt to rescue any failed #806 hypothesis.

Frozen input authority:

- source PR: `#806`
- canonical physical artifact: `autonomous-structural-edge-exhaustion-v3`
- artifact ID: `9005119965`
- artifact ZIP SHA-256: `b00f8aeebc005112c6632a580a3123303c4aa1be64cc6158bfe244a55bb65b4a`
- Stage-6 semantic SHA-256: `2bdf60d6d7d463146f4ac11b4c9078ed04f2cee965d9629858660b1af34e6ae3`
- frozen hypotheses: `648`

The calibration consumes only `stage5_development_outcomes.json`, `stage6_structural_screen.json`, and the frozen final authority metadata. It rejects any event split other than observation / replication / validation.

```text
SEALED_UNOPENED_LOADED=NO
SEALED_UNOPENED_SCORED=NO
FAILED_NEAR_MISS_RESCUE_AUTHORIZED=NO
THRESHOLD_RELAXATION_AUTHORIZED=NO
STRATEGY_PROMOTION_AUTHORIZED=NO
```

PR #809 remains a separate history-first pattern-mining lane and is not modified by this audit.

## 1. What actually killed the 648 hypotheses

The physical Stage-6 attrition is:

| Gate | Passed |
|---|---:|
| Observation n >= 20 | 648 / 648 |
| Observation absolute mean >= 2 bps | 147 / 648 |
| Replication n >= 10 | 648 / 648 |
| Replication mean >= 2 bps | 187 / 648 |
| Replication hit rate >= 55% | 181 / 648 |
| Replication 90% bootstrap mean-CI lower bound > 0 | 62 / 648 |
| **All non-BH Stage-6 gates simultaneously** | **12 / 648** |
| **Campaign-wide BH q <= 2.5%** | **0 / 648** |

Minimum observed replication sign-test p-value:

`0.0007813946724140139`

Minimum campaign-wide BH q-value:

`0.30916765019804143`

This proves that the campaign was not simply 648 completely flat hypotheses. Twelve hypotheses satisfied every frozen Stage-6 requirement except the campaign-wide multiplicity gate, while 62 had a positive replication bootstrap mean-CI.

No one of those hypotheses is promoted by this observation.

## 2. Dense planted-edge recovery

Diagnostic construction:

1. center each hypothesis's observation and replication directional-excess distribution to zero;
2. add the same known positive effect to every hypothesis;
3. rerun the frozen Stage-6 semantics and the same 648-hypothesis BH denominator.

| Planted effect | BH passes | Full Stage-6 recovered | Recall |
|---:|---:|---:|---:|
| +2 bps | 0 / 648 | 0 / 648 | 0.0% |
| +5 bps | 239 / 648 | 207 / 648 | 31.9% |
| +8 bps | 526 / 648 | 525 / 648 | 81.0% |
| +15 bps | 644 / 648 | 644 / 648 | 99.4% |

This rejects the hypothesis that the code is an unconditional always-fail machine. Large effects are recoverable.

It also shows poor power for modest effects even under the favorable case where all hypotheses are non-null.

## 3. Sparse planted-edge recovery

A more realistic calibration plants exactly **one true hypothesis in each of the 18 information families** while the remaining hypotheses are centered nulls.

For each effect size, 200 deterministic trials select one hypothesis per family. The same 648-test BH denominator and frozen Stage-6 gates are retained.

| Planted effect | Mean recall | Median recall | P10–P90 | Mean false positives |
|---:|---:|---:|---:|---:|
| +2 bps | 0.0% | 0.0% | 0.0%–0.0% | 0.000 |
| +5 bps | 3.83% | 0.0% | 0.0%–11.11% | 0.000 |
| +8 bps | 41.0% | 38.89% | 27.22%–55.56% | 0.000 |
| +15 bps | 91.97% | 94.44% | 83.33%–100.0% | 0.000 |

This is the most important calibration result.

Under the current sample sizes and 648-test campaign-wide multiplicity burden:

- a sparse +2 bps structural effect is effectively undetectable;
- a sparse +5 bps effect is almost always missed;
- a sparse +8 bps effect is detected less than half the time on average;
- a sparse +15 bps effect is usually detected.

Therefore `0 / 648` cannot by itself rule out economically modest sparse effects.

## 4. Representative full-lane recovery through Stage 8

One deterministic median-replication-n hypothesis per information family was planted, with non-plants centered to zero. The synthetic records were then passed through the **existing** Stage-6 structural screen, Stage-7 validation/WFA, and Stage-8 robustness functions.

The unopened Stage 9 was never called.

| Plant | Stage 6 | Stage 7 | Stage 8 |
|---:|---:|---:|---:|
| +2 bps | 0 / 18 | 0 / 18 | 0 / 18 |
| +5 bps | 1 / 18 | 1 / 18 | 1 / 18 nominal* |
| +8 bps | 8 / 18 | 8 / 18 | 8 / 18 |
| +15 bps | 17 / 18 | 17 / 18 | 17 / 18 |

`*` The +5 bps plant sits mathematically on the robustness lane's extra-cost boundary: base cost is 5 bps and robust cost is 10 bps. After centering, the high-cost expectation should be exactly zero. The current code checks `mean > 0.0` with no numerical tolerance, so tiny floating-point residuals can classify an exact-zero boundary as positive. This is a minor numerical robustness defect to repair separately; it did **not** cause the original #806 zero-survivor result because no real candidate reached Stage 8.

## 5. Null-world calibration

A deterministic null diagnostic was run for 1,000 worlds.

Method:

- apply one global session-level Rademacher sign flip to raw excess outcomes;
- preserve cross-hypothesis/session dependence through the shared session sign;
- reselect direction using observation only;
- recompute replication sign p-values and the full 648-test BH correction;
- evaluate the remaining frozen Stage-6 gates only for BH candidates.

Results:

```text
NULL_WORLDS=1000
WORLDS_WITH_ANY_BH_PASS=16
TOTAL_BH_PASSES=19
FULL_STAGE6_FALSE_POSITIVES=1
FULL_STAGE6_FALSE_POSITIVE_COUNT_PER_WORLD=0.001
```

The current screen is therefore conservative under this null diagnostic rather than obviously false-positive-prone.

This null test is diagnostic, not a formal proof of all possible dependence structures.

## 6. Hit-rate p-value versus mean-targeting p-value

The frozen global BH input is a one-sided binomial sign test of:

```text
P(return > 0) > 0.5
```

That is not the same hypothesis as:

```text
E[excess return] > 0
```

A synthetic asymmetric control makes the semantic difference explicit:

```text
40 trades at +20 bps
60 trades at -5 bps
mean = +5 bps
hit rate = 40%
```

For this distribution:

- current one-sided sign p: `0.9823998998911476`
- current 55% hit-rate gate: `FAIL`
- mean-targeting centered-bootstrap p: `0.0004997501249375312`

So the current screen intentionally excludes positive-expectancy, low-hit-rate payoff shapes.

However, this mismatch is **not the sole explanation for the real #806 result**.

A diagnostic one-sided centered session-bootstrap test targeting positive replication mean was computed across the actual 648 hypotheses:

```text
RAW_MEAN_BOOTSTRAP_P_LT_0_05=54
RAW_MEAN_BOOTSTRAP_P_LT_0_025=32
MINIMUM_MEAN_BOOTSTRAP_P=0.0004997501249375312
MINIMUM_MEAN_BOOTSTRAP_BH_Q=0.3238380809595202
BH_Q_LE_10PCT=0
BH_Q_LE_5PCT=0
BH_Q_LE_2_5PCT=0
```

Therefore changing the p-value target from hit rate to mean return would **not** produce a certified survivor on the already-consumed #806 corpus after multiplicity correction.

That is an important negative finding: the sign-test semantics are questionable for general edge discovery, but they are not a hidden switch that turns the existing near-misses into certified strategies.

## 7. Interpretation

The calibration supports all of the following simultaneously:

1. **No obvious always-fail coding defect.** The certifier recovers sufficiently large planted effects.
2. **Strong false-positive control.** The null-world screen produced only one full Stage-6 false positive across 1,000 diagnostic worlds.
3. **Material sparse-edge power problem.** +2/+5 bps effects are almost invisible under the current 648-test design; +8 bps is recovered only about 41% of the time when sparse.
4. **The sign-test definition is narrower than positive expectancy.** This is a methodology limitation, but replacing it diagnostically with a mean-targeting bootstrap test still leaves zero BH survivors on the real #806 data.
5. **Representation/data authority remains unresolved.** This calibration does not repair the 81-symbol coverage-selected constituent proxy, lack of point-in-time NIFTY membership/weights, equal-weight information representation, KMeans state-motif abstraction, or fixed 15/30/60-minute horizons.
6. **The #806 negative result should be narrowed.** It strongly rejects large/frequent/high-hit effects expressible through its frozen representation. It does not establish that no modest, sparse, asymmetric, differently timed, or differently represented edge exists in the historical market.

## 8. Parallel lane with PR #809

PR #809 is correctly kept separate.

```text
PR806 calibration
= does the microscope detect known signal and reject nulls?

PR809 history-first miner
= can a different outcome-blind representation expose recurring structures missed by the old state-motif representation?
```

Neither lane is authorized to tune against #806 near misses or inspect the unopened #806 tail.

## Current calibration authority

`PR806_CERTIFIER_FUNCTIONAL_BUT_SPARSE_MODEST_EDGE_DETECTION_UNDERPOWERED`

This does **not** authorize:

- relaxing the frozen #806 gates;
- reopening failed #806 hypotheses;
- promoting any of the 12 pre-BH near misses;
- opening the 63-session sealed tail;
- strategy integration;
- paper/live execution;
- orders.
