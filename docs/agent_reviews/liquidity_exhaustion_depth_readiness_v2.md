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
- zero missing, non-numeric, nonpositive-LTP or negative bid/ask rows;
- bid and ask size columns, or a non-null structured depth/order-book field;
- quote dates must have corresponding candle authority.

## Completed immutable-corpus result

The audit completed twice with identical semantic hashes on producer commit `66b5342345b70cb439352b35a6d65581ba495a5c`.

Classification: `DEPTH_DATA_NOT_READY_FOR_EXHAUSTION_DISCOVERY`

Observed:

- 129 quote/depth files;
- 2,778,666 quote rows;
- only one session, `20260709`;
- zero future unseen holdout sessions;
- approximately 372 minutes of session coverage;
- aggregate median timestamp gap approximately 0.904 seconds;
- aggregate p95 timestamp gap approximately 1.807 seconds;
- all 129 files contain a non-null structured `depth` field;
- top-level bid/ask authority is unusable: zero active top-of-book rows;
- 2,618,670 rows failed the preregistered top-level price-validity contract.

Blockers:

- `DEVELOPMENT_SESSION_COUNT_BELOW_MINIMUM:1<60`
- `FUTURE_UNSEEN_HOLDOUT_SESSION_COUNT_BELOW_MINIMUM:0<20`
- `INVALID_PRICE_ROW_RATE_TOO_HIGH`
- `NO_ACTIVE_TOP_OF_BOOK_ROWS`

## Next permitted work

A separate schema-forensics campaign may inspect the nested `depth` payload and determine whether top-of-book prices and sizes can be normalized without inference or fallback. Even if that succeeds, strategy discovery remains blocked until the development and future-holdout session requirements are satisfied.

## Result boundary

`DEPTH_DATA_READY_FOR_EXHAUSTION_DISCOVERY` would mean only that a later preregistered microstructure hypothesis can be studied. It would not prove an edge. The completed result does not permit strategy construction, paper/live promotion, or execution.