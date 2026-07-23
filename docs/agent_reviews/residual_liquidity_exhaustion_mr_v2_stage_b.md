# Residual Liquidity Exhaustion Mean Reversion V2 — Stage B Stability Audit

mode: RESEARCH_REJECTION_AUDIT_ONLY  
campaign_id: RESIDUAL_LIQUIDITY_EXHAUSTION_MR_V2  
stage: B_PATTERN_STABILITY_AUDIT  
stage_a_base_commit: 11e3241d1f78305726e4a9c35c8c23b059f6132b  
strategy_created: false  
structural_edge_claim_allowed: false  
profitability_claim_allowed: false  
paper_live_allowed: false  
execution_allowed: false

## Why Stage B exists

Stage A emitted 491 development events. The overall raw residual event and the immediate candle-based exhaustion confirmation both had negative average reversion at every measured horizon. Freezing a trading strategy from the best-looking Stage A segment without a family-wide stability audit would be post-outcome cherry-picking.

Stage B therefore acts only as a rejection screen. It cannot certify an edge. A survivor is merely a diagnostic candidate that must receive a newly frozen equation and genuinely unseen data.

## Frozen candidate family

The audit evaluates both raw-event entry and next-bar confirmed entry over the Stage A dimensions that were already declared before this audit:

- overall;
- symbol;
- symbol and shock side;
- symbol and time bucket;
- symbol and residual-magnitude bucket;
- symbol and volatility bucket.

It does not search new thresholds, indicators, feature combinations, exits or option parameters.

## Frozen gates

A candidate survives only when all gates pass:

1. At least 40 events across at least 30 sessions.
2. Mean, median and positive rate are favorable at 5, 15, 30 and 60 minutes.
3. At least three half-year periods contain 12 or more events, and every eligible period is favorable at 15 and 30 minutes.
4. Session-equal-weight sign-flip tests at 15 and 30 minutes both survive Benjamini-Hochberg correction at FDR 0.05 across the complete candidate family.
5. Magnitude and volatility bucket candidates also require an adjacent eligible bucket with favorable 15- and 30-minute behavior.
6. The complete audit must match across the two independently generated Stage A event ledgers.

These gates are deliberately conservative because Stage A outcomes are already visible. The audit may reject the formulation; it may not convert a development segment into a profitability claim.

## Decision boundary

- No survivors: `NO_STABLE_RESIDUAL_MEAN_REVERSION_SEGMENT_FOUND`; close the candle-residual formulation and continue collecting valid depth data.
- One or more survivors: `DIAGNOSTIC_SEGMENTS_FOUND_REQUIRES_NEW_PREREGISTRATION_AND_UNSEEN_DATA`; freeze a separate candidate equation before touching new data.

The historical depth lane remains unusable because the archived bid and ask arrays are empty. Liquidity-exhaustion discovery therefore remains dependent on the isolated Upstox depth shadow-capture campaign.
