# Provenance Gate Decision

Authority: `3eb04c13f6a1d8d0320e4e0d3be8cdbcad6011ba`

`research_only=true`, `runtime_authority=NONE`, `broker_actions=0`.

Decision: `PROVENANCE_INSUFFICIENT_FAIL_CLOSED`

- `HTF_CERTIFICATION_AUTHORIZED=false`
- `COMMON_FACTOR_EXACT_RERUN_AUTHORIZED=false`
- No certification or candidate rerun was started.

HTF remains `ROBUSTNESS_REQUIRED`: the exact historical data directory, CSV source set, invocation, trade/event ledger, and cost/slippage definitions were not proven. The committed positive and negative summaries are therefore classified `INSUFFICIENT_EVIDENCE`.

Common-factor remains `ROBUSTNESS_REQUIRED`: the frozen resolver/source bytes and an authoritative coherent prior-run lineage were not recovered. Holdout integrity is `UNKNOWN`; absence of a holdout ledger was not treated as preservation.

No strategy, runtime, broker, credential, registry, or threshold files were modified.
