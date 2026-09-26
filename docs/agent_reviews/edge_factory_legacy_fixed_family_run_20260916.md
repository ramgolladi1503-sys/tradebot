# Legacy Fixed-Family Edge Factory Run — Custody / Search-Debt Record

Status: **NOT CERTIFIABLE — PRESERVE AS SEARCH HISTORY**

Observed legacy research commit:

```text
fc755df5b8b50b7224e8c788ee984ce349fe4351
```

Campaign identity reported by the run:

```text
TRADEBOT_AUTONOMOUS_2026_EDGE_FACTORY_V1
```

This run predates / does not satisfy the outcome-blind discovery architecture now proposed by `TRADEBOT_RESEARCH_TRUTH_LAYER_V1`.

## Custody decision

The run must not be deleted and must not be represented as a certified Edge Factory result.

It is preserved for two reasons:

1. it documents hypotheses whose outcomes have already been inspected;
2. those attempts contribute to cumulative search / selection pressure in later campaigns.

At minimum the run contributes:

```text
families_observed=8
primary_cells_observed=32
validation_candidates_reported=1
confirmed_survivors=0
```

The 32 observed primary cells must be imported into the cumulative experiment/search ledger before any later outcome-blind campaign performs global selection adjustment.

This is a **minimum incremental search-debt contribution from this run**, not a statement that earlier TradeBot research had only 32 trials. Older campaigns must also be reconstructed/imported where evidence exists.

## Why this run is not certifiable

The logged implementation contains material truth-layer violations, including repeated family-level hard-coded values:

```text
max_fold_contribution = 0.40
delay_5m_ratio = 0.55
```

It also repeatedly defines incremental lift as the absolute partial Spearman correlation minus the absolute marginal baseline Spearman correlation. Those are not the same out-of-sample metric and therefore do not establish the required baseline-vs-candidate incremental lift.

The family code applies Holm/BH to the raw feature-target correlation p-values while the research claim is incremental conditional information. The multiplicity statistic therefore does not cleanly correspond to the claimed hypothesis.

The F2 candidate freeze also records `negative_controls_passed=true` as a literal freeze value rather than deriving admission directly from governed negative-control evidence.

The run further used a predefined eight-family catalog and proceeded directly through those fixed families. It did not produce/prove the required outcome-blind `MECHANISM_CATALOG` freeze before outcome access.

Therefore:

```text
scientific_certification_authority=false
family_no_edge_verdicts_authoritative=false
validation_survivor_authoritative=false
confirmation_result_certifying=false
search_history_consumed=true
```

## F2 confirmation custody

The run opened its protected confirmation partition for:

```text
F2_H4_OR30_RANGE_EXPANSION_60M
```

That confirmation data is now **consumed for that exact hypothesis** and may never be relabeled pristine confirmation for a future re-test of the same candidate.

The failed result remains historical evidence, but because the admission/evaluation harness was defective it does not create a clean certification verdict.

Any future campaign that independently rediscovers an overlapping opening-range mechanism must:

- declare overlap explicitly;
- count the legacy attempt in global search pressure;
- not reuse the consumed F2 confirmation block as pristine confirmation;
- obtain a genuinely protected future confirmation stream if the mechanism survives a valid evaluation.

## Discovery firewall for future campaigns

Outcome-blind discovery must not read the legacy run's effect sizes, p-values, best candidate, near-miss rankings, or failure patterns to invent new mechanisms.

Discovery may receive only non-outcome custody metadata such as:

```text
prior_campaign_exists=true
prior_family_fingerprints=<opaque identities>
prior_primary_trial_count_increment=32
specific_confirmation_block_consumed=true
```

Phase B / global search-accounting code may access the detailed prior ledger after the new mechanism catalog is frozen.

This separation prevents prior outcomes from steering mechanism discovery while still preserving selection-bias accounting.

## Governance consequence

Do not merge the legacy research branch as proof of a certified Edge Factory.

Do not delete it either.

Treat it as an append-only historical research artifact and search-debt source.

The next valid campaign must use:

```text
OUTCOME_BLIND_DISCOVERY
-> CATALOG_SHA256_FREEZE
-> CERTIFIED_COMMON_KERNEL
-> FALSIFICATION
```

under the draft truth-layer governance in PR #908.

## Safety

```text
read_only_market_research=true
is_order_action=false
broker_api_called=false
order_authority=false
allowed_for_live_execution=false
```
