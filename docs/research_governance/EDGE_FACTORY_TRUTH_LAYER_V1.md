# TradeBot Edge Factory Truth Layer V1

Status: **DRAFT GOVERNANCE PROPOSAL**

This document defines the permanent research truth layer for bounded TradeBot strategy-discovery campaigns. It exists to prevent future agents, prompts, scripts, or researchers from silently changing the rules after seeing outcomes.

The machine-readable authority is:

`research/governance/edge_factory_truth_layer_v1.json`

## 1. What is permanent vs disposable

The following distinction is mandatory:

- **Truth layer:** durable research authority derived from robustness, walk-forward, false-discovery, holdout, market-structure, and execution-separation principles.
- **Campaign:** a finite catalog of hypotheses/families tested under the truth layer.
- **Strategy:** disposable. Most are expected to fail.
- **Survivor:** rare. Must satisfy every applicable truth-layer gate.

A strategy result may never redefine the truth layer that judged it.

## 2. Literature-derived doctrine

The V1 truth layer encodes the following principles:

- Kaufman: mechanism before optimized rule; broad robustness and parameter plateaus over isolated optima.
- Chan: establish statistical behavior before strategy construction; chronology matters.
- Harris: distinguish information propagation from contemporaneous restatement; do not claim microstructure without microstructure evidence.
- Sinclair: separate underlying predictability from option monetization and execution.
- Aronson: falsifiable hypotheses, objective rules, null hypotheses, and negative controls.
- Pardo: chronological walk-forward evaluation and visible bad folds.
- López de Prado / Bailey: search itself creates overfitting; protect holdouts, account for trials, PBO/selection risk where applicable.
- Carver: prefer simple, independently validated forecasts; diversify only after individual survival.
- Ilmanen: expect regime dependence; do not assume stationarity.
- FWER/FDR literature: correct for multiple testing and preserve complete search history.

These principles are research law, not optional suggestions.

## 3. Historical evidence boundary

V1 defaults to `OHLCV_ONLY` historical authority.

Historical bid/ask, spread, depth, fills, latency, OI, IV, or Greeks are not assumed unless a separate source is independently proven authoritative.

Never synthesize bid/ask or depth for certification.

Historical option candles may support `HISTORICAL_OPTION_CANDLE_RESEARCH_ONLY`; they do not create execution-grade evidence.

## 4. Common research kernel

Every Edge Factory family must use the same certified kernel for:

- timestamp semantics and causal bar availability;
- chronological partitioning;
- protected confirmation custody;
- baseline-vs-candidate scoring using the same metric;
- Holm/BH and other multiplicity controls;
- session-block bootstrap;
- fold/session concentration;
- actual +5m/+10m delay recomputation;
- negative controls;
- code/data/partition provenance;
- append-only experiment ledgers.

A family may implement its own feature logic, but it may not reimplement these gates independently.

## 5. Explicitly forbidden harness behavior

The following are contract violations:

- hard-coded negative-control passes;
- hard-coded delay ratios;
- hard-coded concentration values;
- applying multiplicity correction to a statistic different from the incremental hypothesis being claimed;
- comparing unlike metrics and calling the difference incremental lift;
- reading protected confirmation before candidate freeze;
- allowing future outcomes into feature matrices;
- reporting the base SHA as executed code provenance when research code is dirty or different;
- silently deleting failed experiments from the ledger.

A critical truth-layer defect invalidates the affected certification path until repaired and re-certified.

## 6. Bounded V1 family catalog

The campaign universe is exactly:

1. `F1_OPENING_GAP_INVENTORY_RESPONSE`
2. `F2_OPENING_PRICE_DISCOVERY_AND_RANGE_TRANSITION`
3. `F3_VOLATILITY_STATE_TRANSITION`
4. `F4_PATH_EFFICIENCY_TREND_VS_EXHAUSTION`
5. `F5_INTRADAY_EXTREME_DISPLACEMENT_RESPONSE`
6. `F6_CROSS_INDEX_INFORMATION_PROPAGATION`
7. `F7_SCHEDULED_EVENT_RESPONSE`
8. `F8_FUTURES_SPOT_PROPAGATION_REEVALUATION`

Limits:

- maximum 8 primary families;
- maximum 8 primary tests per family;
- maximum 64 primary cells total;
- no family 9;
- no new family because prior families failed;
- no post-outcome gate weakening;
- no post-failure indicator/filter addition;
- no failed-signal inversion promoted as a new strategy.

The target of 3 independent survivors is a portfolio target, **not a requirement to manufacture three strategies**.

## 7. Prior-family custody

V1 preserves prior research state:

- constituent breadth/diffusion: closed, no robust edge;
- option-implied vs realized: closed, no defendable phenomenon;
- futures/spot OHLCV v1: quarantined because the harness was defective; one clean re-evaluation is allowed through the certified common kernel;
- Tuesday/0DTE OHLCV v1: quarantined because the harness was defective; re-evaluation is deferred in this campaign.

Closed families may not be retuned by a future strategy PR.

## 8. Required family protocol

Every family follows:

`mechanism -> frozen hypotheses -> formation -> validation -> multiplicity -> effect size -> incremental baseline -> chronological stability -> actual delay -> negative controls -> candidate freeze -> locked confirmation -> portfolio independence -> option translation -> prospective registry`

A failed family is retired and the bounded campaign advances. Failure does not authorize inversion, filtering, or threshold hunting.

## 9. Stop rules

### Success

Stop new-family discovery when three **independent confirmed mechanism clusters** survive the applicable historical gates, portfolio-independence analysis is complete, option-candle translation is attempted where possible, and prospective registries are created.

### Exhaustion

If all eight families are executed, blocked, retired, or confirmed with fewer than three independent survivors, stop anyway and report the exact number honestly.

### Global blocker

Stop the campaign if the common kernel cannot be certified, shared authoritative data is unusable, protected evidence is irreparably contaminated, or continuation would require fabrication, unsafe mutation, or broker/order authority.

## 10. Change control

V1 may not be semantically edited in place by ordinary strategy/research PRs.

A semantic change requires all of the following:

1. a new version (for example V2), not silent mutation of V1;
2. a dedicated governance PR;
3. explicit rationale tied to methodology/data-authority change, not strategy performance;
4. adversarial review;
5. update of the contract hash and anti-drift tests;
6. preservation of V1 history and results.

This means a future agent cannot say “the old gate was too strict because nothing survived” and weaken it inside the same campaign.

## 11. Safety boundary

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

A `SURVIVOR` is research evidence, not broker authority.
