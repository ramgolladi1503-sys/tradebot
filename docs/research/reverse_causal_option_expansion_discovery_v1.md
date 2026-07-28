# Reverse-Causal Option Expansion Discovery V1

This package is a research-only, stage-gated evidence scaffold for discovering BUY-only index-option premium-expansion mechanisms by working backward from historical option-premium expansions.

It does not modify production strategies, broker integration, live execution, risk management, feed handling, configuration, dashboards, or frozen research campaigns.

Required safety flags:

- `research_only=true`
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `append=false`

## Files

- `scripts/run_reverse_causal_option_expansion_discovery.py`: deterministic preflight runner and research package writer.
- `tests/research/test_reverse_causal_option_expansion_discovery.py`: fail-closed tests for data authority, non-action flags, and timestamp causality.
- Runtime outputs are written under `runtime/research/reverse_causal_option_expansion_v1/` and are not intended for production wiring.

## Stage Gates

The runner separates evidence tiers:

- Stage A Source Integrity: actual bytes, non-pointer sources, deterministic paths, hashes, schema and timestamp validation, and real option identity.
- Stage B Causal Structural Discovery: valid option OHLCV, CE/PE identity, strike/expiry identity, causal timestamps, and no future leakage. Spread/depth are not mandatory.
- Stage C Gross Outcome Evaluation: Stage B plus next-observation entry semantics and conservative candle-label handling.
- Stage D Assumption-Based Cost Stress: conservative declared cost assumptions only; never observed spread evidence.
- Stage E Execution Certification: authoritative timestamp-aligned bid/ask or defensible quote-derived spread. Depth is required only when the intended fill model needs size-level impact evidence.
- Stage F Final Validated Edge: frozen mechanism, untouched holdout, authoritative execution-cost evidence, independent audit, robustness controls, and deterministic reproduction.

Missing quote/spread authority blocks Stage E/F, but it does not invalidate Stage B/C structural and gross evidence when source integrity is valid.

The current full run produced:

- Initial screen: `NO_DISCRIMINATIVE_PRECURSOR_IN_INITIAL_FEATURE_SCREEN`
- 1,997,159 eligible labelled observations
- 60,392 raw expansion-event rows
- 11,261 independent move clusters
- 178,521 matched ordinary controls
- 100,983 near-miss controls
- 0 accepted precursors for freeze

The deep sequence and cross-sectional pass tested 10 controlled definitions across 10 families and returned:

`NO_DISCRIMINATIVE_PRECURSOR_IN_TESTED_FAMILIES`

Coverage:

- Option OHLCV first timestamp: `2024-09-26 09:15:00+05:30`
- Option OHLCV last timestamp: `2026-07-21 15:28:00+05:30`
- Distinct sessions: `390`
- Distinct expiries: `82`
- Distinct instruments: `1199`
- CE contracts: `549`
- PE contracts: `650`
- Independent move clusters: `11261`
- `runtime/strategy_validation/resolved_option_ticks_20260702.parquet` contains one resolved-tick session, `2026-07-02`, with `876127` rows. It is not the full option-OHLCV coverage source.

Four deep definitions showed high event-versus-matched-control lift, but none passed the freeze gate because they either had insufficient event coverage or failed near-miss discrimination. No mechanism was frozen and the holdout remained unopened.

## Run

```bash
python scripts/run_reverse_causal_option_expansion_discovery.py
python scripts/run_reverse_causal_deep_sequence_search.py
python scripts/audit_reverse_causal_option_expansion_outputs.py
pytest -q tests/research/test_reverse_causal_option_expansion_discovery.py
```

## Migration Notes

No runtime migration is required. This is an offline research artifact only.
