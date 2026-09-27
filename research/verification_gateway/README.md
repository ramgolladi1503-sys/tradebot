# Reuse-first strategy verification gateway: isolated first integration

**Status: experimental; NOT wired to discovery, backtesting, brokerage, certification, or protected ledgers.**
A passing unit test is neither source-fidelity proof nor research authorization.

This branch intentionally does not touch frozen root `requirements.txt`,
`pyproject.toml`, live runtime code, canonical outcomes, or governed workflows.
GitHub main may differ materially from the user's local, dirty research worktree;
reconcile those changes before any merge.

## What exists already (reuse before replacement)

- `core/strategy_spec.py`: EDGE-65 metadata-only StrategySpec registry.
- `core/strategy_hypothesis_contracts.py`: EDGE-67 read-only research hypothesis contracts.
- `core/research_pipeline.py`: existing diagnostics; it must not be treated as a
  protected-OOS evaluator without separate authority and independent review.
- `requirements.txt`: Hypothesis is ALREADY declared. Do not install duplicates
  or introduce a second application-wide dependency list.

The new `ResearchStrategySpec` is a **source-fidelity supplement**, not a
replacement for the live/paper metadata registry. `existing_registry_strategy_id`
may reference EDGE-65, but no adapter or authorization is claimed yet.

## Adopted building blocks

- Pydantic v2: explicit source provenance, rule/assumption distinctions,
  reviewed-source evidence, canonical digest, schema rejection.
- Pandera: synthetic OHLCV fixture shape/order/range checks, not market truth.
- Hypothesis: property-based synthetic causal-order regression tests.

Install separately for research tests in an isolated environment using
`requirements-verification.txt`; resolve a reproducible lock before promotion.

```sh
python -m venv .venv-research-verify
. .venv-research-verify/bin/activate
python -m pip install -r research/verification_gateway/requirements-verification.txt pytest pandas
PYTHONPATH=. python -m pytest -q tests/research/test_verification_gateway_contracts.py tests/research/test_verification_gateway_data.py
```

**Test outputs have not been independently produced in this branch yet.**
Do not claim green until the exact branch is executed in a safe isolated checkout.

## Deliberately not imported

- Freqtrade: study its lookahead-analysis ideas; do not copy GPL code into
  TradeBot without a deliberate distribution/license decision. Its native
  strategy/exchange assumptions are not equivalent to NSE options.
- NautilusTrader and QuantConnect LEAN: evaluate one independently on a
  small synthetic execution-parity fixture; do not add two large production
  backtesting engines or rewrite TradeBot. Instrument-specific options fills
  still need authoritative historical quotes.
- Third-party purged CV repository: inspect maintenance, license, test leakage
  with independent synthetic overlapping-label fixtures, and prefer existing
  validated local capabilities when sufficient. No external statistical
  package automatically repairs exposure of previously viewed outcomes.

## Mandatory follow-up integration sequence

1. Reconcile the current dirty local worktree with GitHub main and the latest
   root-cause report; do not overwrite local-only research fixes.
2. Review this prototype against current protected-ledger access boundaries.
   Make schema validation evidence-based: caller-provided boolean flags are
   explicitly UNTRUSTED placeholders and must be replaced by signed or
   independently produced verifier artifacts (content hashes, fixture and
   implementation digests, and reviewer provenance).
3. Add an adapter mapping `ResearchStrategySpec.existing_registry_strategy_id`
   to EDGE-65 without importing/executing strategy modules. Preserve EDGE-65
   safety semantics; fail closed on nonexistent or conflicting IDs.
4. Add independent reference-vs-production signal/event comparison, as well
   as property-based future-data metamorphic tests. Include known timing
   failure #1 and translation mismatch #17 using original verified fixtures.
5. Integrate causal time + data provenance + cost authority checks as mandatory
   read-only preregistration gates for official research entry points. Audited
   access must not be bypassable through normal public APIs. Filesystem access
   isolation is a separate deployment constraint.
6. Profile the existing research pipeline independently; inspect its Monte
   Carlo implementation and post-hoc regime-selection workflow before using
   either for certification. Make no historical outcome mutation.
7. Validate one independently specified synthetic strategy end to end, then
   one existing EXPOSED research strategy as an engineering-only pilot. An
   existing exposed backtest is never an untouched OOS confirmation.
8. Require separate adversarial acceptance and immutable evidence review.
   Only then classify the system as ready for a *controlled strategy hunt*.
   This cannot guarantee a profitable strategy.

## Explicit stage gate

Until follow-up integration and safe CI succeed, this prototype remains
`NOT_INTEGRATED_NOT_CERTIFIED`. It must never be imported as an authorization
mechanism or used by broker/runtime code.
