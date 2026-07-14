# STRATEGY TRUTH PHASE 2B

## IMPLEMENTATION DIRECTION

RIGHT

## approved objective

Apply a uniform fail-safe policy for missing market evidence without changing setup definitions, thresholds or complete-context behavior.

## what was implemented

- Removed missing-as-positive scoring in `failed_breakout_trap`, `exhaustion_reversal`, `vwap_reclaim`, and `core.option_confirmation`.
- Tightened thesis-evidence gating so missing structure/compression/expansion anchors no longer pass through `trend_pullback`, `compression_breakout`, `mean_reversion_extension`, or `event_volatility_expansion`.
- Added a focused Phase 2B test suite at `tests/test_strategy_missing_evidence_policy.py`.
- Preserved the Phase 1A-2A complete-context fingerprint and left runtime StrategyContext truth mapping untouched.

## architecture assessment

- `ARCHITECTURE CHANGE: NONE`
- No new registry, service, database, event bus, config file, or state machine was added.
- Changes stayed inside existing movement generators, one shared movement helper, one read-only option-confirmation module, one new focused test file, and this evidence document.

## starting commit

- Starting commit: `db19774008db93671c8a24b93f98cb7488498ad2`
- Phase 0: `cf2d74bc7a2938a08bc651e25b5334481479d68c`
- Phase 1A: `9ace90c0b49d790f0e8926a75ecd9492ae6d3b26`
- Phase 1B: `2a247ec6d92f60aa101d462eb6f3013d1aec4d54`
- Phase 1C: `e74bbac98cfb3db43e15129bc78be4bb47564c45`
- Phase 2A: `db19774008db93671c8a24b93f98cb7488498ad2`

## files changed

- `strategies/movement/_utils.py`
- `strategies/movement/trend_pullback.py`
- `strategies/movement/compression_breakout.py`
- `strategies/movement/event_volatility_expansion.py`
- `strategies/movement/mean_reversion_extension.py`
- `strategies/movement/failed_breakout_trap.py`
- `strategies/movement/exhaustion_reversal.py`
- `strategies/movement/vwap_reclaim.py`
- `core/option_confirmation.py`
- `tests/test_strategy_missing_evidence_policy.py`
- `docs/agent_reviews/strategy_truth_phase2b_missing_evidence.md`

## complete evidence-classification matrix

| component | input field(s) | classification | old missing behavior | new missing behavior | blocking | warning emitted | complete-context result | runtime-path effect |
|---|---|---|---|---|---|---|---|---|
| `OPENING_DRIVE` | `minutes_since_open`, `open_price`, `vwap`, `spot_ltp` | `REQUIRED_THESIS_EVIDENCE` | Already blocked | Unchanged | Yes | No | Unchanged | None |
| `OPENING_RANGE_RETEST` | `minutes_since_open`, `orb_high`, `orb_low`, `vwap`, `spot_ltp` | `REQUIRED_THESIS_EVIDENCE` | Already blocked | Unchanged | Yes | No | Unchanged | None |
| `COMPRESSION_BREAKOUT` | `range_width_pct`, `atr_short`, `atr_long` | `REQUIRED_THESIS_EVIDENCE` | Regime score could satisfy compression without direct compression evidence | Compression score becomes `0.0`; candidate suppressed | Yes | No | Unchanged | Missing compression inputs now remove the candidate |
| `COMPRESSION_BREAKOUT` | breakout level, VWAP alignment | `REQUIRED_THESIS_EVIDENCE` | Already blocked by price checks | Unchanged | Yes | No | Unchanged | None |
| `TREND_PULLBACK` | `nearest_support` or `nearest_resistance` | `REQUIRED_THESIS_EVIDENCE` | Fell back to `vwap` as anchor | Missing structure anchor blocks candidate | Yes | No | Unchanged | Runtime contexts missing support/resistance no longer emit pullback candidates |
| `TREND_PULLBACK` | trend regime score | `REQUIRED_THESIS_EVIDENCE` | Already blocked by threshold | Unchanged | Yes | No | Unchanged | None |
| `VWAP_RECLAIM_REJECTION` | `vwap`, `spot_ltp`, confirmation metadata or previous spot | `REQUIRED_THESIS_EVIDENCE` | Already blocked | Unchanged | Yes | No | Unchanged | None |
| `VWAP_RECLAIM_REJECTION` | `vwap_slope` | `OPTIONAL_CORROBORATION` | Missing slope added `0.5` alignment | Missing slope contributes `0.0` | No | Yes: `missing_optional_evidence:vwap_reclaim_rejection_v1:vwap_slope` | Unchanged | Runtime score can decrease but not increase when slope is absent |
| `FAILED_BREAKOUT_TRAP` | ORB/day/structure re-entry fields | `REQUIRED_THESIS_EVIDENCE` | Already blocked | Unchanged | Yes | No | Unchanged | None |
| `FAILED_BREAKOUT_TRAP` | trend-side premium stall | `OPTIONAL_CORROBORATION` | Missing premium counted as perfect stall | Missing premium contributes `0.0`; explicit non-positive premium still counts as stall | No | No | Unchanged | Score decreases or candidate disappears when stall evidence is absent |
| `EXHAUSTION_REVERSAL` | `spot_ltp`, `vwap`, stretch window | `REQUIRED_THESIS_EVIDENCE` | Already blocked | Unchanged | Yes | No | Unchanged | None |
| `EXHAUSTION_REVERSAL` | trend-side premium stall | `OPTIONAL_CORROBORATION` | Missing premium counted as full stall | Missing premium contributes `0.0` | No | No | Unchanged | Score decreases or candidate disappears |
| `EXHAUSTION_REVERSAL` | `volume_z` fade evidence | `OPTIONAL_CORROBORATION` | Missing volume counted as full fade | Missing volume contributes `0.0` | No | No | Unchanged | Score decreases or candidate disappears |
| `MEAN_REVERSION_EXTENSION` | support/resistance or day boundary anchor | `REQUIRED_THESIS_EVIDENCE` | Candidate could emit with no boundary anchor | Missing boundary now blocks candidate | Yes | No | Unchanged | Runtime contexts missing range anchors now suppress the candidate |
| `MEAN_REVERSION_EXTENSION` | continuation evidence | `INVALIDATION_EVIDENCE` | Missing continuation already scored zero, not positive | Unchanged | Threshold path | No | Unchanged | None |
| `EVENT_VOLATILITY_EXPANSION` | `atr_short`, `atr_long`, `volume_z` | `REQUIRED_THESIS_EVIDENCE` | Regime/volatility-state could satisfy expansion with missing ATR or volume | Expansion score becomes `0.0`; candidate suppressed | Yes | No | Unchanged | Missing ATR or volume now removes the candidate |
| `LATE_DAY_MOMENTUM` | `minutes_since_open`, `minutes_to_close`, `vwap`, `spot_ltp` | `REQUIRED_THESIS_EVIDENCE` | Already blocked | Unchanged | Yes | No | Unchanged | None |
| `LATE_DAY_MOMENTUM` | `volume_z` | `OPTIONAL_CORROBORATION` | Already scored zero when missing | Unchanged | No | No | Unchanged | None |
| `OPTION_QUOTE_CONFIRMATION` | side quote LTP, premium, spread, depth, age, fallback | `DOWNSTREAM_OPTION_EVIDENCE` | Missing same-side evidence already blocked; missing opposite premium inflated weakness score | Missing opposite premium now contributes zero weakness; same-side missing evidence still blocks | Same-side only | Existing side warnings only | Unchanged | Pressure score no longer increases from absent opposite premium |
| `NO_TRADE_CHOP` | N/A | `NOT_USED` | Safety suppression only | Unchanged | N/A | N/A | Unchanged | None |

## verified missing-as-positive defects

- `FAILED_BREAKOUT_TRAP`: missing CE/PE premium was treated the same as explicit stall.
- `EXHAUSTION_REVERSAL`: missing premium was treated the same as explicit stall.
- `EXHAUSTION_REVERSAL`: missing `volume_z` was treated the same as explicit fade.
- `VWAP_RECLAIM_REJECTION`: missing `vwap_slope` added non-zero alignment.
- `OPTION_QUOTE_CONFIRMATION`: missing opposite-side premium inflated dominant-side pressure.
- `TREND_PULLBACK`: missing structure anchor could still emit via `vwap` fallback.
- `COMPRESSION_BREAKOUT`: missing direct compression fields could still emit from regime score alone.
- `MEAN_REVERSION_EXTENSION`: missing range boundary could still emit.
- `EVENT_VOLATILITY_EXPANSION`: missing ATR or volume could still emit from regime state alone.

## false audit leads

- `OPENING_DRIVE` already blocked on missing timing, open price, VWAP, and spot.
- `OPENING_RANGE_RETEST` already blocked on missing timing and ORB fields.
- `LATE_DAY_MOMENTUM` already blocked on missing timing and core directional fields.
- The candidate-pool orchestrator already contained generator failures without aborting other generators.
- Phase 2A runtime StrategyContext propagation remained truthful; no Phase 2A file edits were required.

## shared policy

- Required thesis evidence missing or non-finite: emit no candidate for that component.
- Optional corroboration missing: contribute zero positive evidence.
- Missing optional evidence must not raise the raw score.
- Missing evidence is never converted into `0`, `0.5`, `1.0`, current price, or another fabricated positive substitute.
- One blocked or empty generator must not abort the rest of the pool.

## field-specific validators

- Prices and anchors: finite and `> 0`
- ATR fields: finite and `> 0`
- Premium change: finite; `0` remains a valid observed value but is not positive confirmation
- Spread: finite and `>= 0`
- Depth: finite and `>= 0`, with the existing minimum applied separately
- Volume z-score: finite; `0` and negative values remain valid observed values
- Minutes: finite; boundary zero remains valid
- `None`, `NaN`, `inf`, and `-inf`: invalid for required market evidence

## per-generator changes

- `trend_pullback`: removed the fallback from structure anchor to `vwap`; setup now requires explicit support/resistance anchor.
- `compression_breakout`: direct compression inputs (`range_width_pct` and ATR ratio) are required before regime compression can matter.
- `event_volatility_expansion`: direct ATR ratio and volume evidence are required before regime expansion can matter.
- `mean_reversion_extension`: explicit range boundary anchor is required before extension reversion can emit.
- `failed_breakout_trap`: missing premium now means no stall contribution.
- `exhaustion_reversal`: missing premium and missing volume now mean no stall/fade contribution.
- `vwap_reclaim`: missing slope now contributes zero and emits a deterministic warning.
- `core.option_confirmation`: missing opposite premium no longer counts as weakness.

## complete-context fingerprint

Preserved exactly:

```text
opening_range_retest_v1
0.639513
BUY_CALL
VALIDATED_CANDIDATE

compression_breakout_v1
0.675169
BUY_CALL
VALIDATED_CANDIDATE

trend_pullback_v1
0.719646
BUY_CALL
VALIDATED_CANDIDATE

option_pressure_confirmation_v1
0.814750
BUY_CALL
VALIDATED_CANDIDATE
```

## runtime before/after

- Before: several generators could still emit when direct runtime evidence remained missing because missing structure, compression, expansion, stall, fade, or slope evidence was treated as neutral or positive.
- After: those same missing fields either block the affected component or contribute zero positive evidence. Other generators continue to run.

## expected candidate removals

- `TREND_PULLBACK` can disappear when runtime support/resistance is missing.
- `COMPRESSION_BREAKOUT` can disappear when runtime range-width or ATR ratio is missing.
- `MEAN_REVERSION_EXTENSION` can disappear when no real range boundary is available.
- `EVENT_VOLATILITY_EXPANSION` can disappear when ATR ratio or volume evidence is missing.
- `FAILED_BREAKOUT_TRAP`, `EXHAUSTION_REVERSAL`, and `VWAP_RECLAIM_REJECTION` can score lower or disappear when corroboration is absent.

## unexpected changes

- None found in complete direct-context behavior.
- No generator-order or pool-failure-containment regressions were observed in the focused suite.

## focused tests and counts

- Command:

```bash
python -m pytest -q \
  tests/test_strategy_missing_evidence_policy.py \
  tests/test_strategy_context_truth.py \
  tests/test_strategy_profile_fail_closed.py \
  tests/test_strategy_profile_integrity.py \
  tests/test_candidate_pool.py \
  tests/test_candidate_pool_quality.py \
  tests/test_candidate_pool_orchestrator.py \
  tests/test_candidate_pool_contract_snapshots.py \
  tests/test_opening_movement_strategies.py \
  tests/test_compression_trend_movement_strategies.py \
  tests/test_vwap_trap_movement_strategies.py \
  tests/test_exhaustion_mean_reversion_strategies.py \
  tests/test_event_late_day_movement_strategies.py \
  tests/test_option_confirmation.py \
  tests/test_no_trade_engine.py \
  tests/test_strategy_generators_lineage.py \
  tests/test_movement_registry.py
```

- Result: `141 passed, 1 warning`
- Additional search for requested phrases only found non-movement contract/remediation references; no extra Phase 2B movement-runtime tests were required beyond the focused set.

## static checks

- `python -m py_compile strategies/movement/_utils.py strategies/movement/*.py tests/test_strategy_missing_evidence_policy.py`
- `ruff check strategies/movement tests/test_strategy_missing_evidence_policy.py`
- `git diff --check`
- Result: all passed

## full-suite result

- Command: `python -m pytest -q`
- Result: `5688 passed, 1 failed, 1 deselected`

## first failure

- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- Observed error text:

```text
RuntimeError:[AUTH] missing_kite_access_token
Missing token at /Users/madhuram/tradebot-strategy-truth-foundation/.runtime/kite_access_token
Run scripts/kite_autologin_localhost.py to refresh token.
```

- Classification: pre-existing orchestrator credential-path failure, identical to the previously established baseline failure from the Phase 2A reproduction.

## risks

- Runtime candidate counts can drop where Phase 2A still leaves truthful gaps in support/resistance, ATR, or range-width sources.
- Optional-missing warnings are only surfaced where a candidate still exists; fully blocked components do not emit a separate warning artifact in this phase.
- `core.movement_regime.py` still uses heuristic regime scores; this phase intentionally did not redesign that regime layer.

## rollback

- Revert the Phase 2B commit only. No data migration, config migration, or shared-checkout cleanup is required.

## explicit non-claims

- No strategy threshold was tuned.
- No setup sequence was rewritten.
- No ranking, no-trade, execution, broker, feed, dashboard, backtesting, or WFA logic was changed.
- No new market-data producer or indicator source was added.
- No claim is made about tradable edge, profitability, or pattern validity.
- No claim is made that missing Phase 2A runtime sources are now available; missingness is only handled more safely.
