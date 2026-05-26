# EDGE-80 — NoTradeOracle

## Purpose

EDGE-80 adds the canonical no-trade explanation layer.

The oracle answers one question:

`Why should the bot not trade right now, based on evidence that already exists?`

It is deliberately not an execution gate, dashboard feature, strategy scorer, feed recovery tool, or runtime writer.

## Inputs consumed

The oracle can consume these existing read-only evidence sources:

- canonical feed-health truth
- feed hold gate evidence
- market-close feed state evidence from HOTFIX/EDGE-79B
- live indicator readiness diagnostics from HOTFIX/EDGE-79A
- opportunity scoring evidence
- candidate ranking evidence
- executable-truth evidence

## Output

`build_no_trade_oracle_report(...)` returns a `NoTradeOracleReport` with:

- `status`
- `no_trade_required`
- `primary_reason`
- ordered `reasons`
- `blockers`
- `warnings`
- `evidence_sources`
- explicit read-only and no-append markers
- explicit non-action markers

## Deterministic priority

Reasons are sorted by severity first, then by category and reason code.

Highest priority examples:

1. missing evidence fails closed
2. market closed
3. websocket disconnected or unsafe feed state
4. feed health / feed hold
5. executable truth blocks
6. indicator readiness blocks
7. no scored/ranked/executable candidates

## Fail-closed behavior

If no evidence is supplied, the oracle returns:

- `status=NO_TRADE_REQUIRED`
- `primary_reason=missing_no_trade_evidence`

This is intentional. A no-trade oracle that allows trading when evidence is missing is worse than useless; it creates fake safety.

## Scope guard

This PR does not:

- place orders
- create order intent
- call external execution APIs
- reconnect feeds
- resubscribe tokens
- compute indicators
- score opportunities
- rank candidates
- mutate runtime
- append files
- change dashboard behavior

## Example report meaning

Example no-trade explanation:

`No trade because market/feed close-state evidence says MARKET_CLOSED, and indicator readiness is blocked for NIFTY because OHLC bars are below warmup and VWAP/RSI/EMA/ATR are missing.`

That is better than a vague `no candidate` or `feed disconnected` message because the report preserves the evidence path.

## Test command

`PYTHONPATH=. python -m pytest tests/test_edge_80_no_trade_oracle.py`

## Next PR

EDGE-81 — NoTrade Evidence in Review Queue/UI.

EDGE-81 may display this evidence, but it must not change the oracle contract or add execution behavior.
