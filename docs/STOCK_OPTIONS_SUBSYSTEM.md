# Stock Options Subsystem

This subsystem introduces a disciplined, liquidity-aware stock options pipeline.

Key guarantees:
- Hard liquidity filters (OI, volume, spread, quote freshness)
- Deterministic candidate selection (ATM-focused, limited strikes/expiries)
- Explicit candidate status (executable / advisory / blocked)
- No impact on existing pipeline unless enabled

Integration note:
- Controlled via ENABLE_STOCK_OPTIONS flag
- Designed to plug into candidate builder stage
