# EDGE-91 — Regime Replay Scenarios

## Purpose

EDGE-91 adds deterministic, read-only replay scenarios for market-regime classification.

The goal is to prove that known market snapshots fall into the expected regime buckets before later PRs build feed-fault replay, strategy proof packs, end-to-end edge acceptance, paper-only gates, live-pilot controls, or final readiness reports.

## Scope

In scope:

- Define canonical replay scenarios for regime classification.
- Replay snapshot sequences through the existing `core.market_state.build_market_state(...)` contract.
- Derive stable regime IDs from trend, volatility, breadth, liquidity, and session dimensions.
- Verify expected dimensions and expected regime IDs.
- Verify expected regime transition counts for multi-step scenarios.
- Fail closed on invalid scenarios, invalid snapshots, or insufficient market-state evidence.
- Emit read-only, non-action evidence payloads.

Out of scope:

- Strategy selection.
- Candidate ranking.
- Runtime wiring.
- Dashboard/UI work.
- Broker/adaptor interaction.
- Paper journal mutation.
- Feed-fault replay.
- Strategy replay proof packs.
- End-to-end edge acceptance.

## Contract

Module:

- `core.regime_replay_scenarios`

Primary function:

- `build_regime_replay_report(scenarios=None, symbol="MARKET", mode="PAPER")`

Default scenario factory:

- `default_regime_replay_scenarios()`

Primary report:

- `RegimeReplayReport`

Scenario/step models:

- `RegimeReplayScenario`
- `RegimeReplayStep`
- `RegimeReplayScenarioResult`
- `RegimeReplayStepResult`

Status values:

- `REGIME_REPLAY_PASSED`
- `REGIME_REPLAY_FAILED`
- `REGIME_REPLAY_BLOCKED`

## Regime ID derivation

Each replay step calls the existing market-state model and derives a regime ID from:

1. `trend`
2. `volatility`
3. `breadth`
4. `liquidity`
5. `session`

Example:

```text
UP_HIGH_BULLISH_DEEP_OPENING
```

When the market-state model returns blockers, the replay step is blocked and the regime ID is forced to:

```text
UNKNOWN
```

That is intentional. Missing evidence must not become a fake regime.

## Canonical scenarios

EDGE-91 ships with two default scenarios:

1. `opening_uptrend_to_midday_range`
   - opening expansion: `UP_HIGH_BULLISH_DEEP_OPENING`
   - midday compression: `SIDEWAYS_LOW_MIXED_NORMAL_MIDDAY`
   - expected transition count: `1`

2. `closing_downtrend_extreme_thin`
   - closing selloff: `DOWN_EXTREME_BEARISH_THIN_CLOSING`
   - expected transition count: `0`

These are not trading strategies. They are deterministic regime-bucket proofs.

## Safety behavior

EDGE-91 is evidence-only.

It does not:

- rank candidates
- select strategies
- submit, modify, cancel, or route broker instructions
- wire runtime behavior
- mutate paper truth
- append events
- update dashboard/UI surfaces

Every report, scenario result, step result, and transition payload includes explicit non-action flags.

## Failure behavior

The replay report fails closed when:

- no scenarios are supplied
- a scenario has no valid steps
- a step has an invalid snapshot
- market-state evidence is insufficient
- actual classifications do not match expected classifications
- actual transition count does not match the expected transition count

## Test proof

Focused tests cover:

- default canonical scenarios passing
- non-action/read-only payload flags
- regime transition derivation
- dimension mismatch failure
- invalid snapshot blocking
- insufficient market-state evidence blocking
- transition-count mismatch failure
- JSON serialization

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_91_regime_replay_scenarios.py -q
```

## Next

EDGE-92 should add feed-fault replay scenarios. Do not combine it into EDGE-91. The clean boundary is important: first prove deterministic regime buckets, then prove feed fault behavior.
