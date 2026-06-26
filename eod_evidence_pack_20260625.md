# End-of-Day Evidence Pack: 2026-06-25

Scope: read-only analysis and generated evidence. No broker APIs called. No orders placed, modified, or canceled. No risk, feed, freshness, strategy, lifecycle, kill-switch, or order gates weakened.

## Files Used

- `.runtime/market_data/ticks_20260625.jsonl`
- `data/active_options_replay.json`
- `.runtime/strategy_no_qualified_reasons_latest.json`
- `.runtime/candidate_starvation_trace_latest.json`
- `.runtime/phase2_rejection_latest.json`
- `.runtime/notrade_reason_truth_latest.json`
- `data/oos_trades.csv`
- `scripts/convert_ticks_to_replay.py`
- `scripts/run_live_replay.py`
- `scripts/run_wfa_intraday.py`

## Tick Data Integrity

| Check | Result |
| --- | --- |
| Raw tick file | `.runtime/market_data/ticks_20260625.jsonl` |
| Raw size | 316.83 MB |
| Raw records | 2,456,551 |
| First tick | `2026-06-25T11:37:58 IST` approx, `BANKNIFTY26JUN57200CE` |
| Last tick | `2026-06-25T15:31:16 IST` approx, `NIFTY BANK` |
| Non-monotonic tick timestamps | 0 |
| Unique symbols | 166 |
| Index ticks present | `NIFTY 50`, `NIFTY BANK` |
| Index ticks absent | `SENSEX`, `INDIA VIX` |

The tick file is structurally usable for NIFTY and BANKNIFTY analysis. It is not sufficient for SENSEX or VIX-backed conclusions.

## Replay Dataset

`data/active_options_replay.json` was regenerated from the settled tick file.

| Check | Result |
| --- | --- |
| Replay snapshots | 13,919 |
| Replay first timestamp | `2026-06-25T11:37:58` |
| Replay last timestamp | `2026-06-25T15:31:16` |
| Contains `NIFTY_INDEX` | yes |
| Contains `BANKNIFTY_INDEX` | yes |
| Contains `SENSEX` / `SENSEX_INDEX` | no |
| Contains `INDIA_VIX` | no |

Authority warning: `scripts/run_live_replay.py` is not a production-equivalent replay. It uses a mock execution router, a dummy risk engine, simplified market data construction, and exception-swallowing around strategy calls. It is useful for diagnostic screening only, not for execution-readiness or fill-quality proof.

## Latest Runtime No-Trade Evidence

The latest runtime artifacts do not currently contain a complete per-symbol strategy table. The strongest current top-level blockers are:

| Artifact | Key Evidence |
| --- | --- |
| `.runtime/strategy_no_qualified_reasons_latest.json` | `not_applicable_reason=feed_blocked`, `raw_candidate_count=0`, `phase2_input_candidate_count=0`, `by_symbol={}` |
| `.runtime/candidate_starvation_trace_latest.json` | `latest_global_blocker=FEED_LTP_STALE`, `first_zero_stage=no_raw_candidates`, `raw_candidate_count=0` |
| `.runtime/phase2_rejection_latest.json` | `phase2_input_count=0`, `phase2_starvation_reason=upstream_starvation` |
| `.runtime/notrade_reason_truth_latest.json` | `feed_fresh=true`, `option_tick_fresh=true`, `phase2_input_candidate_count=0`, `primary_reason=unknown` |

The artifacts show candidate starvation before Phase 2 in the latest cycle. They do not prove that each named strategy independently qualified and then failed. They prove the live chain did not deliver Phase 2 input candidates.

## Last Candidate Funnel Snapshot

The candidate-starvation artifact also preserves an earlier same-session candidate funnel:

| Symbol | Raw Candidates | Post Scan | Post Real Filter | Post Executable Filter |
| --- | ---: | ---: | ---: | ---: |
| BANKNIFTY | 162 | 14 | 14 | 12 |
| NIFTY | 162 | 14 | 14 | 12 |
| SENSEX | 162 | 10 | 10 | 8 |

The last detailed symbol snapshot is SENSEX, but the EOD tick dataset does not include SENSEX index ticks. Treat this SENSEX snapshot as runtime-artifact evidence only, not replay-backed evidence from `ticks_20260625.jsonl`.

SENSEX last-symbol snapshot details:

| Field | Value |
| --- | --- |
| Candidate funnel stage | `post_real_filter_zero` |
| Final emit blocker | `iv_term` |
| Reject reason | `iv_term` |
| Quote health state | `STALE` |
| LTP age | `677.9910809993744` seconds |
| Reject gate reasons | `lifecycle_gate_fail`, `no_signal_planning_fallback_disabled`, `non_live_option_chain`, `no_signal`, `no_candidates_survived`, `STALE_OPTION_TICK` |

This means at least one earlier candidate-generation path produced raw candidates, but the final emitted candidate set still went to zero before Phase 2 acceptance.

## WFA Proxy Research

`data/oos_trades.csv` contains the latest available WFA proxy output.

| Metric | Value |
| --- | ---: |
| Trades | 782 |
| Total PnL | -596,858.33 |
| Win rate | 56.01% |
| Average PnL | -763.25 |
| `is_oos` flag | all `False` |

Strategy split:

| Strategy | Trades |
| --- | ---: |
| TrendVWAP | 429 |
| ORB | 324 |
| MeanReversion | 29 |

Authority warning: `scripts/run_wfa_intraday.py` reads historical NIFTY futures OHLCV from `data/aeron7_data`, resamples to 5-minute bars, and uses `core.backtesting.wfa.WalkForwardAnalyzer`. It is proxy directional research. It does not replay today's option tick data, real option bid/ask execution, or the production Phase 2 gate chain. It should not be used as proof that a live option strategy has edge.

The negative WFA result is still useful as a warning: the current directional proxy stack does not show robust expectancy after slippage.

## Algo-Trader Interpretation

For a noisy, range-bound, or high-entropy session, a disciplined algo trader should not force directional entries. The safe choices are:

1. Stand aside if directional edge is not measurable.
2. Trade only a separately validated range/chop strategy with tight invalidation.
3. Use volatility-harvesting structures only if IV, liquidity, margin, event-risk, and exits are explicitly modeled and approved.

The current bot appears to have capital-preservation behavior. It does not yet have a proven, authorized playbook for unstable range or volatility-harvesting regimes.

## Where The Bot Is Lacking

1. No validated strategy availability matrix for regimes such as `UNSTABLE_RANGE`, `HIGH_ENTROPY_RANGE`, or `EVENT`.
2. No production-equivalent EOD replay harness that reuses the same live decision path end to end.
3. No replay-backed SENSEX/VIX evidence in the current tick dataset.
4. Proxy WFA is negative and has an `is_oos` labeling inconsistency.
5. MeanReversion has too few proxy trades and poor proxy performance to justify loosening live gates.

## What Not To Change

Do not weaken:

- LTP freshness gates
- option freshness gates
- entropy/regime stability gates
- lifecycle gates
- Phase 2 execution-quality gates
- risk, broker, kill-switch, or live-order gates

Zero trades in a noisy market is acceptable if the evidence says no validated edge exists.

## Recommended Next PR Scope

Title: Production-equivalent EOD decision replay and no-trade evidence pack.

Allowed scope:

- Add a replay harness that feeds captured ticks into the same live decision/orchestrator path without broker/order side effects.
- Emit a per-symbol, per-cycle decision table: feed state, regime, strategy attempted, raw candidates, Phase 2 input, final blocker.
- Mark unsupported regimes explicitly as `NO_VALIDATED_STRATEGY_FOR_REGIME`.
- Add tests proving replay is read-only, broker-free, and does not weaken gates.

Out of scope:

- Strategy threshold tuning
- Risk gate relaxation
- Feed freshness changes
- Broker/order adapter changes
- Short-premium live enablement

## Run Instructions

```bash
python3 scripts/convert_ticks_to_replay.py .runtime/market_data/ticks_20260625.jsonl
python3 scripts/run_live_replay.py
python3 scripts/run_wfa_intraday.py
```

Interpret `run_live_replay.py` and `run_wfa_intraday.py` as diagnostic/proxy tools only until a production-equivalent replay harness is added.
