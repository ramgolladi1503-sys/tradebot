# Provider Sparse-Bar Governance V1

Final verdict: `DISCOVERY_READY`

The four missing NIFTY one-minute bars are governed as provider-authoritative absences. The observed warehouse remains observed-only: no synthetic candles, no interpolation, and no forward-filled underlying prices.

Structural discovery must consume only `research_eligible=true` rows. Sparse-bar handling is centralized in warehouse eligibility metadata, not in strategies.
