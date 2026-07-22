# Liquidity Exhaustion Depth Readiness V2

mode: RESEARCH_DATA_READINESS_ONLY  
campaign_id: LIQUIDITY_EXHAUSTION_DEPTH_READINESS_V2  
base_commit: fa502c07425c67a9f2ba440a20900d772db82689  
strategy_created: false  
edge_claim_allowed: false  
execution_allowed: false

## Objective

Determine whether the immutable quote/depth corpus is capable of supporting a causal liquidity-exhaustion discovery equation. This audit does not search for profitable rules.

## Frozen readiness requirements

- at least 60 independent development sessions;
- at least 20 later unseen sessions reserved for eventual confirmation;
- at least 300 minutes of intraday coverage per session;
- aggregate median quote gap no greater than 5 seconds;
- aggregate p95 quote gap no greater than 30 seconds;
- crossed-market rate no greater than 0.1%;
- bid and ask size columns, or a non-null structured depth/order-book field;
- quote dates must have corresponding candle authority.

## Audit outputs

For every quote/depth file, record schema, timestamps, cadence, duplicates, source ordering, symbol/token authority, top-of-book validity, spread distribution, crossed/locked markets and depth capability. Run the complete audit twice and require semantic equality.

## Result boundary

`DEPTH_DATA_READY_FOR_EXHAUSTION_DISCOVERY` means only that a later preregistered microstructure hypothesis can be studied. It does not prove an edge. `DEPTH_DATA_NOT_READY_FOR_EXHAUSTION_DISCOVERY` blocks strategy construction and identifies the missing acquisition requirements.
