# Aixion Trade Intelligence — CAS-A1 Post-Close Analytics

## Purpose

This runbook integrates the frozen CAS-A1 auction-surprise hypothesis into the read-only Aixion Trade Intelligence evidence kernel.

It is a research/prospective-evidence lane only.

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
```

No strategy, ranking, risk, approval, broker, execution, or order path is changed.

## Frozen research contract

```text
expected_CAS_adjustment_bps
=
15.5350561749
+
2.9081599522 * equal_weight_constituent_return_1510_1514_bps
```

After the final CAS index result is causally available:

```text
auction_surprise_bps
=
realized_CAS_adjustment_bps
-
expected_CAS_adjustment_bps
```

Prediction:

```text
surprise > 0 -> UP
surprise < 0 -> DOWN
surprise == 0 -> NO_PREDICTION
```

No refit, threshold search, dead-band, feature substitution, tick-to-minute inference, forward fill, instrument substitution, or timestamp shifting is permitted under `CAS_A1_FROZEN_PROSPECTIVE_V1`.

## Evidence architecture

```text
governed completed-minute / post-close evidence
  -> scripts/build_cas_a1_postclose_observation.py
  -> exact source-parity observation JSON
  -> scripts/finalize_cas_a1_intelligence_session.py
  -> CAS_A1_EXPECTATION_FROZEN
  -> CAS_FINAL_PRICE_OBSERVED
  -> CAS_A1_SURPRISE_OBSERVED
  -> CAS_A1_PREDICTION_FROZEN
  -> CAS_A1_OUTCOME_OBSERVED
  -> same PR790 canonical JSONL evidence stream
  -> immutable prospective result
  -> daily Markdown analytics
  -> cumulative prospective summary
```

The source adapter does not infer minute closes from arbitrary ticks. Every frozen constituent must supply an explicit completed 15:10 bar and completed 15:14 bar. NIFTY must supply an explicit completed 15:14 bar. The final CAS price and 15:29/15:39 futures marks must be explicit point evidence with preserved causal availability timestamps.

The adapter fails closed on missing bars, incomplete bars, duplicate/ambiguous bars, mixed providers, cross-session timestamps, non-positive/non-finite prices, or missing required point marks.

## Source-bundle contract

The source bundle contains:

- `session_id`
- `session_date`
- `index_instrument`
- `futures_instrument`
- exact frozen `analytics_contract.cas_a1`
- `completed_minute_bars`
- `point_marks`

Each completed-minute bar requires:

```json
{
  "instrument_key": "<exact instrument key>",
  "minute": "15:10",
  "close": 123.45,
  "available_time": "<causal timestamp>",
  "source_event_id": "<immutable evidence id>",
  "source_provider": "<single governed provider>",
  "bar_complete": true
}
```

Point marks use labels `FINAL_CAS`, `15:29`, and `15:39` for the exact index/futures instruments.

Missing values are never converted to zero.

## Build the exact post-close observation

```bash
cd /Users/madhuram/tradebot
source .venv-cas-fetch/bin/activate

PYTHONPATH=. python scripts/build_cas_a1_postclose_observation.py \
  --bundle .runtime/aixion_trade_intelligence/cas_a1/source_bundles/YYYY-MM-DD.json \
  --output .runtime/aixion_trade_intelligence/cas_a1/inbox/YYYY-MM-DD.json
```

A successful adapter run proves only that the supplied evidence satisfies the frozen source-parity contract. It does not prove the upstream producer actually observed a live market session; source provenance must remain independently governed.

## Finalize the session

Run after all 15:39 futures evidence has been durably persisted, normally around 15:50 IST.

```bash
PYTHONPATH=. python scripts/finalize_cas_a1_intelligence_session.py \
  --input .runtime/aixion_trade_intelligence/cas_a1/inbox/YYYY-MM-DD.json \
  --events .runtime/aixion_trade_intelligence/YYYY-MM-DD/events.jsonl \
  --output-root .runtime/aixion_trade_intelligence/cas_a1/prospective
```

Or use the daily wrapper, which performs both stages:

```bash
TRADEBOT_ROOT=/Users/madhuram/tradebot \
CAS_A1_PYTHON=/Users/madhuram/tradebot/.venv-cas-fetch/bin/python \
./scripts/run_cas_a1_postclose_daily.sh
```

If the source bundle is absent or empty, the wrapper returns `NO_VALID_SESSION_INPUT` and does not score the hypothesis. This is the required exchange-holiday/failed-capture behavior.

## Outputs

```text
.runtime/aixion_trade_intelligence/cas_a1/inbox/YYYY-MM-DD.json
.runtime/aixion_trade_intelligence/cas_a1/prospective/
  sessions/YYYY-MM-DD_CAS_A1_FROZEN_PROSPECTIVE_V1.json
  YYYY-MM-DD_CAS_A1_REPORT.md
  cumulative_summary.json
```

The canonical CAS events are appended to the supplied PR790 event JSONL.

Identical reruns are idempotent at the prospective-result layer and canonical event IDs are deterministic. A semantic conflict for an existing session/spec must fail closed.

## Development/prospective separation

Development evidence remains:

```text
2026-08-03 through 2026-08-14
10 sessions
9/10 directional development observation
unadjusted exact p ~= 0.0238
selection-contaminated
```

Prospective evidence begins only after the frozen specification.

Never pool development and prospective counts.

## Scheduling boundary

The intended machine-local timer is 15:50 IST on weekdays. The repository contains the deterministic daily runner, but it does not install or enable a `launchd` job because machine-specific paths, environment, and credentials remain operator-controlled.

The scheduler must invoke only the post-close wrapper. It must never start trading, modify/cancel/place orders, or change execution authority.

## Claim boundary

A successful post-close run proves only that the frozen calculation and evidence publication completed for that session.

It does not prove:

```text
HISTORICAL_EDGE_SUPPORTED
OUT_OF_SAMPLE_SUPPORTED
EXECUTION_VIABLE
PROSPECTIVE_SUPPORTED
STRUCTURAL_EDGE_CERTIFIED
```
