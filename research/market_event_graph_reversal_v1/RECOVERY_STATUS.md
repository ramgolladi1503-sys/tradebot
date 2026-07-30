# Market Event Graph Recovery Status

## Recovered without retuning

The original evidence archive is `causal-market-state-v1-evidence-v3.zip` with SHA-256:

`fde3f5c74f12bf59d80d39012bffd89a9411954b9207561f92b792ade31099b3`

The frozen graph dataset has SHA-256:

`30f3d399404a299da6cb99b600a3f2b7346deb74653d5f4a8ebf8849ebefe73c`

Primary CE graph:

```text
breadth_down_1:HIGH
-> index_breadth_divergence:LOW
-> breadth_down_1:LOW
-> CE
```

Protocol recovered from the original report:

- chronological 60/20/20 split by session;
- graph semantics `A(t-2) -> B(t-1) -> C(t)`;
- `LOW` and `HIGH` derived from training-only 20th/80th percentiles;
- one-bar delayed entry;
- 15-bar holding period;
- 15-minute cooldown;
- 2 bps round-trip cost assumption.

Original CE evidence:

- training occurrences: 168;
- validation: 115 trades, mean 0.0005983524, win rate 0.6173913043, PF 2.4567905524;
- holdout: 25 trades, mean 0.0024606548, win rate 0.64, PF 4.1738554594.

Secondary PE graph is also preserved in `frozen_discovery_spec.json`.

## Exact reproduction result

The original Parquet has now been recovered from the verified archive and reproduced
without discovery, retuning, broadening, or substitution.

Recovered CE thresholds:

- `breadth_down_1` p20: `0.10121457489878542`
- `breadth_down_1` p80: `0.21862348178137653`
- `index_breadth_divergence` p20: `-0.000238836424541256`

Preserved secondary PE thresholds:

- `breadth_up_1` p20: `0.09716599190283401`
- `volume_shock_share` p80: `0.2793522267206478`
- `breadth_mean_ret1` p20: `-0.00019076586779298327`

The reproduction command is:

```bash
python scripts/reproduce_market_event_graph_reversal_v1.py --archive /Users/madhuram/Downloads/causal-market-state-v1-evidence-v3.zip
```

Generated evidence lives under:

```text
research/market_event_graph_reversal_v1/
├── frozen_thresholds.json
├── frozen_strategy_contract.json
├── dataset_manifest.json
├── split_manifest.json
├── reproduction_report.json
├── ledgers/
│   ├── ce_train.csv
│   ├── ce_validation.csv
│   └── ce_holdout.csv
├── reproduction_command.txt
└── SHA256SUMS
```

## Prohibited actions

- Do not guess numerical thresholds.
- Do not re-run the 11,258-combination search to obtain replacement thresholds.
- Do not select thresholds from validation, holdout, July option data, or live data.
- Do not promote to auto execution.

Current truthful status:

```text
EXACT_UNDERLYING_DISCOVERY_REPRODUCED
NOT_OPTION_PREMIUM_VALIDATED
NOT_INDEPENDENTLY_CERTIFIED
SHADOW_ADVISORY_ONLY
```
