# Executive Verdict

Principal verdict: `VERTICAL_SLICE_NOT_CERTIFIED`

Selected strategy: `compression_breakout_v1`.

Scenarios: `33`. Certified: `12`. Not certified/policy-blocked/unresolved: `21`.

Sub-verdicts:

- feed/data integrity: `PARTIALLY_VERIFIED`
- market-state integrity: `PARTIALLY_VERIFIED`
- selected strategy: `PARTIALLY_CERTIFIED`
- TradeBuilder: `NOT_CERTIFIED`
- Phase 1: `PARTIALLY_VERIFIED`
- Phase 2: `PARTIALLY_VERIFIED`
- candidate pool: `PARTIALLY_CERTIFIED`
- risk/executable truth: `PARTIALLY_VERIFIED`
- ranking: `PARTIALLY_CERTIFIED`
- UI authority: `DEFECT_CONTAINED_IN_HARNESS_NOT_PRODUCTION_FIXED`
- approval binding: `PARTIALLY_VERIFIED`
- order intent: `PARTIALLY_VERIFIED`
- broker idempotency: `MOCK_VERIFIED_ONLY`
- order tracking: `MOCK_VERIFIED_ONLY`
- reconciliation: `MOCK_VERIFIED_ONLY`
- observability: `PARTIALLY_VERIFIED`
- determinism: `VERIFIED`
- independent audit: `PASSED_ORACLE_BUT_NOT_ALL_SCENARIOS_CERTIFIED`

No live broker API was called and no real order was placed.
