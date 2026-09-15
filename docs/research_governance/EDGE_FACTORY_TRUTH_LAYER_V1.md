# TradeBot Edge Factory Truth Layer V1

Status: **DRAFT GOVERNANCE PROPOSAL**

This document defines the permanent research truth layer for TradeBot strategy discovery. Its central rule is simple:

> **Freeze the scientific process, not a permanent list of strategies.**

The machine-readable authority is:

`research/governance/edge_factory_truth_layer_v1.json`

## 1. Permanent truth layer vs temporary campaign

The following separation is mandatory:

- **Truth layer:** durable methodology derived from robustness, falsification, walk-forward, false-discovery, holdout, market-structure and execution-separation principles.
- **Discovery phase:** outcome-blind generation of plausible mechanism families from literature, available data authority, market structure and known prior-family identity.
- **Campaign catalog:** a finite set of discovered mechanisms and pre-registered hypotheses, frozen and hashed before forward outcomes are accessible.
- **Strategy:** disposable. Most are expected to fail.
- **Survivor:** rare. Must satisfy every applicable truth-layer gate.

A strategy result may never redefine the truth layer that judged it.

## 2. Literature-derived doctrine

V1 encodes these principles:

- Kaufman: mechanism before optimized rule; broad robustness and parameter plateaus over isolated optima.
- Chan: establish statistical behavior before strategy construction; chronology matters.
- Harris: distinguish information propagation from contemporaneous restatement; do not claim microstructure without microstructure evidence.
- Sinclair: separate underlying predictability from option monetization and execution.
- Aronson: falsifiable hypotheses, objective rules, null hypotheses and negative controls.
- Pardo: chronological walk-forward evaluation and visible bad folds.
- López de Prado / Bailey: search itself creates overfitting; protect holdouts, account for trials, use PBO/search-adjusted inference where applicable.
- Carver: prefer simple independently validated forecasts; diversify only after individual survival.
- Ilmanen: expect regime dependence; do not assume stationarity.
- FWER/FDR literature: correct for multiple testing and preserve complete search history.

These principles constrain how research is performed. They do **not** permanently prescribe which market mechanisms must be tested.

## 3. Outcome-blind autonomous mechanism discovery

Autonomous mechanism discovery is allowed and expected.

Before any forward-return, validation, locked-confirmation, Sharpe, win-rate or strategy-P&L result is exposed, the discovery agent may inspect only:

- literature and research doctrine;
- available field names and data authority;
- data coverage and timestamp semantics;
- market structure and exchange rules;
- identities/status of already closed or quarantined research families;
- non-outcome data-quality diagnostics.

The discovery agent must not inspect:

- forward-return results;
- validation or confirmation results;
- strategy P&L;
- Sharpe/win-rate results;
- best-threshold/best-horizon results;
- near-miss failures as inspiration for a replacement family in the same campaign.

The purpose is to let the agent think freely about plausible mechanisms without letting outcomes steer what gets invented.

## 4. Campaign catalog freeze

Each campaign must produce a finite mechanism catalog **before outcome access**.

Default V1 budget:

```text
max mechanism families = 12
max primary hypotheses per family = 4
max primary horizons per hypothesis = 2
max primary cells total = 96
```

The campaign may discover fewer mechanisms if fewer are scientifically justified.

Before testing begins, materialize a catalog artifact containing at minimum:

```text
campaign_id
mechanism_id
mechanism_name
literature_or_market_rationale
required_data_authority
falsifiable_claim
primary_hypotheses
primary_horizons
baseline_definition
expected_failure_interpretation
known_prior-family overlap
```

Then:

1. canonicalize the catalog;
2. compute and record its SHA-256;
3. freeze family ordering and primary-test budget;
4. lock the discovery phase;
5. only then allow outcome evaluation.

After outcome access begins, the catalog cannot expand, reorder, or replace failed families.

## 5. Global search pressure never resets

A new campaign version does not erase previous search.

TradeBot must maintain an append-only global experiment ledger across campaign generations.

Therefore:

```text
EDGE_FACTORY_V2 != fresh statistical universe
EDGE_FACTORY_V3 != fresh statistical universe
```

All prior tried, failed, blocked and superseded experiments remain part of selection-pressure accounting.

Global FDR or equivalent search adjustment is required, with PBO/DSR/search-adjusted inference where applicable.

A campaign name change must never be used to reset trial count.

## 6. Historical evidence boundary

V1 defaults to `OHLCV_ONLY` historical authority.

Historical bid/ask, spread, depth, fills, latency, OI, IV or Greeks are not assumed unless a separate source is independently proven authoritative.

Never synthesize bid/ask or depth for certification.

Historical option candles may support `HISTORICAL_OPTION_CANDLE_RESEARCH_ONLY`; they do not create execution-grade evidence.

## 7. Common research kernel

Every campaign family must use the same certified kernel for:

- outcome-blind discovery/campaign-state custody;
- catalog freeze/hash custody;
- timestamp semantics and causal bar availability;
- chronological partitioning;
- protected confirmation custody;
- baseline-vs-candidate scoring using the same metric;
- Holm/BH and other multiplicity controls;
- global search accounting;
- session-block bootstrap;
- fold/session concentration;
- actual +5m/+10m delay recomputation;
- negative controls;
- code/data/partition provenance;
- append-only experiment ledgers.

A family may implement its own mechanism/feature logic, but may not independently reinvent these truth gates.

## 8. Explicitly forbidden behavior

The following are contract violations:

- discovering new mechanisms after outcome access begins;
- mutating/replacing the catalog after freeze;
- resetting trial/search pressure because a new campaign version was started;
- hard-coded negative-control passes;
- hard-coded delay ratios;
- hard-coded concentration values;
- applying multiplicity correction to a statistic different from the incremental claim;
- comparing unlike metrics and calling the difference incremental lift;
- reading protected confirmation before candidate freeze;
- allowing future outcomes into feature matrices;
- reporting base SHA as executed code provenance when research code differs;
- silently deleting failed or blocked trials;
- adding filters/indicators after a primary failure;
- inverting a failed strategy and calling it a fresh uncounted idea;
- weakening gates because too few strategies survived.

A critical truth-layer defect invalidates the affected certification path until repaired and re-certified.

## 9. Prior-family custody

V1 preserves prior research state:

- constituent breadth/diffusion: closed, no robust edge;
- option-implied vs realized: closed, no defendable phenomenon;
- futures/spot OHLCV v1: quarantined because the earlier harness was defective; it may only be re-evaluated if explicitly pre-registered in a future blind catalog;
- Tuesday/0DTE OHLCV v1: quarantined and deferred.

Closed families cannot be silently repackaged under a new name.

## 10. Required family protocol

Every frozen family follows:

`mechanism -> pre-registered hypotheses -> formation -> validation -> within-family multiplicity -> global search accounting -> effect size -> incremental baseline -> chronological stability -> actual delay -> negative controls -> candidate freeze -> locked confirmation -> portfolio independence -> option translation -> prospective registry`

A failed family is retired and the frozen campaign advances. Failure does not authorize inversion, filtering, threshold hunting or discovery of a replacement family.

## 11. Survivor target and stop rules

The desired portfolio target remains:

```text
3 independent confirmed mechanism clusters
```

This is a target, never a mandate.

### Success

Stop when three independent confirmed mechanism clusters survive and portfolio-independence analysis, option-candle translation where possible, and prospective registries are complete.

### Exhaustion

If the **frozen campaign catalog** is exhausted with fewer than three survivors, stop and report the exact count honestly.

A later V2 campaign may perform a new outcome-blind discovery phase, but prior search pressure remains in the global ledger.

### Global blocker

Stop if the common kernel cannot be certified, shared authoritative data is unusable, protected evidence is irreparably contaminated, the outcome-blind discovery boundary cannot be proven, or continuation requires fabrication/unsafe mutation/order authority.

## 12. Change control

V1 may not be semantically edited in place by ordinary strategy/research PRs.

A semantic methodology change requires:

1. a new truth-layer version;
2. a dedicated governance PR;
3. explicit methodology/data-authority rationale unrelated to strategy performance;
4. adversarial review;
5. updated contract hash/tests;
6. preservation of V1 history and prior search accounting.

A future agent cannot argue that V1 was "too strict" merely because few strategies survived.

## 13. Safety boundary

This truth layer is research-only and never authorizes execution.

```text
read_only_market_research=true
is_order_action=false
broker_api_called=false
broker_write_authority=false
order_authority=false
orders_placed=0
orders_modified=0
orders_cancelled=0
allowed_for_live_execution=false
manual_approval_required=true
```

A research survivor is evidence, not broker authority.
