# Reverse-Causal Option Expansion Discovery V1

Principal verdict: `NO_DISCRIMINATIVE_PRECURSOR`

## Safety Flags

- `research_only=true`
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `append=false`

## Source Coverage

- Source root: `/Users/madhuram/tradebot/runtime/upstox-expired-options-v1`
- Contract inventory rows: `1315`
- Valid contracts: `1199`
- Expiries: `82`
- One-minute option rows declared: `1998358`
- First candle: `2024-09-26 09:15:00+05:30`
- Last candle: `2026-07-21 15:29:00+05:30`
- Source hash: `8b0fc1ad8d02ff0a3c6842b00360c48a370cf2fe56bb75f66cc7ac2d13774abc`

## LFS Findings

- `/Users/madhuram/tradebot-reverse-causal-option-expansion-v1/runtime/strategy_validation/resolved_option_ticks_20260702.parquet`: pointer=`false`, size=`95829241`, sha256=`7ef6dfae7de94a1f52fac97b007259ada769347ff72299e238b6cac43ab54508`

## Capability Matrix

- `A_SOURCE_INTEGRITY`: can_run=`true`, blockers=`[]`
- `B_CAUSAL_STRUCTURAL_DISCOVERY`: can_run=`true`, blockers=`[]`
- `C_GROSS_OUTCOME_EVALUATION`: can_run=`true`, blockers=`[]`
- `D_ASSUMPTION_COST_STRESS`: can_run=`true`, blockers=`[]`
- `E_EXECUTION_CERTIFICATION`: can_run=`false`, blockers=`['AUTHORITATIVE_QUOTE_OR_SPREAD_MISSING']`
- `F_FINAL_VALIDATED_EDGE`: can_run=`false`, blockers=`['AUTHORITATIVE_QUOTE_OR_SPREAD_MISSING', 'FROZEN_MECHANISM_MISSING', 'UNTOUCHED_HOLDOUT_NOT_EXECUTED', 'INDEPENDENT_FINAL_AUDIT_NOT_EXECUTED']`

## Discovery Counts

- Eligible labelled observations: `1997159`
- Raw expansion events: `60392`
- Independent move clusters: `11261`
- Matched ordinary controls: `178521`
- Near-miss controls: `100983`
- Accepted precursors for freeze: `0`

## Decision

Stage B/C structural and gross outcome artifacts may be produced from valid causal option OHLCV. Execution certification and final validated-edge claims remain blocked without authoritative timestamp-aligned quote or spread evidence. No mechanism was frozen and the holdout was not opened.
