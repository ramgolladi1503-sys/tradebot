# Registry Authority Audit

- **Registry Module**: `core/read_only_strategy_registry.py`
- **Canonical Strategy**: `CAS_MORNING_REVERSAL_SHORT_HORIZON_V1`
  - Enabled: True
  - Required Underlyings: `("NIFTY",)`
  - Mode: `advisory_only`
  - Required Feeds: `("SPOT", "FUTURES")`
- **Audit Finding**: Out-of-universe symbols are strictly marked `INAPPLICABLE` and emit zero candidates, conforming with registry authority.
