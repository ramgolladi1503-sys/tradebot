# Liquidity Exhaustion Nested Depth Schema V2

mode: RESEARCH_SCHEMA_FORENSICS_ONLY  
campaign_id: LIQUIDITY_EXHAUSTION_DEPTH_SCHEMA_V2  
parent_readiness_commit: 233b895d0a13752aac8c995c4129e98bbf6cb9e2  
normalizer_created: false  
strategy_created: false  
edge_claim_allowed: false  
execution_allowed: false

## Objective

Inspect the immutable structured `depth` payload across all 129 quote/depth files and determine its exact recurring shape. This campaign may identify explicit price and size fields. It may not infer missing values, select trades, backtest outcomes or relax the completed readiness blockers.

## Method

- use deterministic evenly spaced samples from every file;
- normalize Arrow, numpy, JSON-string, mapping and sequence representations into Python objects;
- publish root types, complete structural signatures, nested path/type coverage, price-like keys and size-like keys;
- publish bounded examples only;
- run the entire probe twice and require semantic equality.

## Result boundary

The only permitted result is a schema description. A later explicit normalizer requires a separate frozen contract and exact oracle tests. Even a valid normalizer cannot overcome the current one-session development corpus or the absence of future unseen holdout sessions.
