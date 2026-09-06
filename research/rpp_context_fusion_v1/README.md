# RPP Context Fusion V1

This campaign does **not** reinterpret AlgoAlpha's Reversal Probability Profile as a literal future reversal probability.

The parent RPP V2 mechanism remains a causal market-memory / location engine:

`confirmed pivots -> historical density zones -> current interaction -> REJECTED / ACCEPTED / RECLAIMED`

V1 tests one additional, pre-frozen question:

> Does a confirmed RPP interaction become materially more useful for the next 15 minutes when independent contemporaneous NIFTY constituent breadth and exact 5-minute NIFTY momentum agree with the RPP direction?

## Frozen context filter

A parent RPP V2 event is admitted only when all are true:

- RPP event already satisfies the frozen `relative density >= 0.65` contract;
- at least 40 constituent symbols are present at the decision timestamp;
- at least 80% of those symbols have an exact same-session `T / T-5m` return;
- absolute unweighted breadth is at least `0.40`;
- breadth sign agrees with the RPP event direction;
- exact 5-minute NIFTY return sign agrees with the RPP event direction.

There is no parameter grid and no event-subtype selection. Cross-sectional dispersion is recorded only as a diagnostic.

The breadth/coverage thresholds were inherited from earlier independently frozen constituent research rather than chosen after examining RPP outcomes.

## Negative control

The same filter is also evaluated with market context from **30 minutes earlier**. This context is already known at the event time but is deliberately time-decoupled. A positive fusion claim requires material uplift over this lagged-context control as well as over the unfiltered parent RPP event set.

## Evaluation

- 15-minute primary horizon;
- 20/30-minute outcome fields remain diagnostic via the parent RPP outcome contract;
- next actual bar open as entry;
- 5 bps round-trip underlying research cost proxy;
- final 63 regular sessions sealed before RPP features, constituent context, or outcomes are constructed;
- 126-session warmup, then 63-session chronological OOS folds;
- positive session-bootstrap lower bound required;
- positive fold stability, hit-rate, concentration, event/session-count, parent-RPP uplift, lagged-control uplift, and positive after-cost mean are all mandatory.

A negative result is a valid experiment result and must not be converted to a pass by post-outcome threshold tuning.

## Run

```bash
python scripts/run_rpp_context_fusion_v1.py \
  --input research/local_evidence_consolidation_v1/external_local_dirs/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/normalized/constituent_index_5m.parquet \
  --output-dir runtime/research/rpp_context_fusion_v1 \
  --cost-bps 5
```

The runner accepts only the governed physical corpus SHA-256:

`ae9645a83cb555899145e04ebe5a961fd130df25cba88a8fc8fd43b986bbfad0`

## Claim boundary

This campaign does not claim:

- an exact copy of AlgoAlpha's Pine source;
- that RPP density is a calibrated future probability;
- official point-in-time NIFTY constituent weighting;
- option P&L or strike-selection validation;
- paper/live/broker authority;
- access to the sealed tail.
