# Market Event Graph Independent Recertification V2

## Objective

Independently recertify the already-frozen Market Event Graph reversal mechanism without rebuilding the research architecture and without rerunning discovery.

This campaign is a thin mechanism adapter over the existing Pattern Atlas certification helpers. It reuses bootstrap confidence intervals, concentration checks, semantic hashing, and evidence-writing utilities. It does **not** copy or fork the full certification stack.

## Frozen mechanism

Primary CE graph, unchanged:

```text
breadth_down_1:HIGH
-> index_breadth_divergence:LOW
-> breadth_down_1:LOW
```

Frozen train-only thresholds, unchanged:

- `breadth_down_1_p20 = 0.10121457489878542`
- `breadth_down_1_p80 = 0.21862348178137653`
- `index_breadth_divergence_p20 = -0.000238836424541256`

No threshold refit, graph search, graph broadening, direction search, or parameter tuning is authorized.

## Source authority

Original evidence archive:

- archive: `causal-market-state-v1-evidence-v3.zip`
- archive SHA-256: `fde3f5c74f12bf59d80d39012bffd89a9411954b9207561f92b792ade31099b3`
- internal dataset: `market_event_graph_discovery_v3/market_event_graph_dataset.parquet`
- dataset SHA-256: `30f3d399404a299da6cb99b600a3f2b7346deb74653d5f4a8ebf8849ebefe73c`

The original dataset contains 524 sessions. Its original chronological holdout ends on `2026-07-22`.

## Why V2 is required

The preserved V1 reproduction records a one-bar delayed entry, but computes economic return from `future_return_15` on the signal row rather than from the recorded delayed entry and exit prices.

The V2 recertifier therefore treats the old economic ledger as historical evidence only until it is reconciled. Execution-proxy return is recomputed directly from prices:

```text
signal = C(t)
entry  = t + 1 bar
exit   = entry + 15 bars = t + 16 bars from C(t)
gross  = exit_close / entry_close - 1
net    = gross - frozen cost
```

`future_return_15` is retained only as a diagnostic field and cannot determine V2 execution economics.

## Consumed-holdout rule

The original holdout was already used to accept/rank the discovered graph after a search over 11,258 graph-direction pairs. It is therefore **not an independent final test** and must never be reopened as if it were untouched.

Corrected train/validation/holdout statistics can be reported as diagnostic evidence, including a multiple-testing diagnostic, but they cannot certify the graph independently.

## Independent-data gate

A positive V2 certification requires a separate dataset whose sessions are all strictly after `2026-07-22`.

Frozen minimum gates:

- at least 45 independent sessions;
- at least 20 fixed-graph trades;
- mean net return at least 2 bps;
- hit rate at least 55%;
- 90% bootstrap mean-CI lower bound greater than zero;
- one-sided sign-test p-value at most 5%;
- chronological fold audit passes;
- robustness audit passes.

Robustness requires:

- positive base mean;
- positive mean at 5 bps cost;
- positive mean after removing the best 10% of trades;
- top-five positive-trade concentration at most 60%.

If no untouched dataset is supplied, the required verdict is:

`INDEPENDENT_MEG_CERTIFICATION_BLOCKED_NO_UNTOUCHED_DATA`

No threshold may be relaxed to avoid that verdict.

## CAS boundary

CAS began on `2026-08-03`.

Any independent data from `2026-08-03` onward is POST_CAS evidence and must not be silently pooled with PRE_CAS evidence. A future executor must report the regime composition and require explicit regime-safe handling before using POST_CAS data for certification.

## Safety boundary

This campaign is research-only.

- no broker calls;
- no orders;
- no execution/risk/ranking changes;
- no strategy-registry promotion;
- no paper/live authority;
- no option-edge claim;
- no merge authorization.

Even a positive underlying V2 result leaves options translation and shadow activation separately blocked until their own evidence gates pass.
