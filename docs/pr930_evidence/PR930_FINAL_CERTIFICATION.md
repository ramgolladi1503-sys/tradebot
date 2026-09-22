# PR #930 Final Certification & Evidence Report

## Executive Summary
This document provides complete, immutable cryptographic certification for PR #930 (`fix/governed-live-observer-recovery-20260922`).
All non-negotiable safety rules under `AGENTS.md` have been preserved. Zero live execution, order placement, or broker write authority has been introduced.

## Terminal Verdict
`PR930_BLOCKED_SMA200_SOURCE_AUTHORITY` (and `PR930_BLOCKED_T1_CLOSE_SOURCE_AUTHORITY`)

### Evidence Rationale
1. **Spot Daily Close (2026-09-22)**: Verified and certified from live observer snapshot `market_snapshot.json` (LTP: `23329.0`, SHA-256: `f2feb19fd45aeb5af1fe3aeeac00e2045a13ad9f165e24547ace64abcaec3706`).
2. **Futures 15:29 Close**: Token `17512194` (`NIFTY26SEPFUT`) was not subscribed during live observation on 2026-09-22. Offline 1-min archives contain 0 bars. In strict accordance with frozen candidate governance (`INTRADAY_OPENING_DRIVE_V1/FROZEN_SPEC.json`), spot price cannot be substituted for futures close. Status: `BLOCKED_SOURCE_AUTHORITY`. Downstream strategy adapter gracefully disables `INTRADAY_OPENING_DRIVE_V1` fail-closed.
3. **SMA-200 Calculation**: Offline data repositories contain daily spot data only up to 2026-07-28; continuous sessions up to 2026-09-21 are absent. The prior hardcoded default `22450.0` has been completely eliminated from the codebase. Status: `BLOCKED_SOURCE_AUTHORITY`. Downstream strategy adapters gracefully disable `S1_MOMENTUM_OVERNIGHT_V1` and `S4_MONDAY_OVERNIGHT_V1` fail-closed.
4. **Independent Oracle**: Materially separate oracle `scripts/verify_t1_prerequisites_oracle.py` independently verifies the generated manifest, proving spot close matches, fake defaults are rejected, and canonical payload SHA-256 matches. Result: `PASS`.
5. **Exact Watermark Reconciliation**: Shutdown protocol asserts conservation `accepted == persisted + rejected + remaining` (`remaining == 0`, `unaccounted_remainder == 0`) across depth, runtime, and tick stores using public getters without private member introspection. Result: `PASS`.
6. **Declarative Strategy Routing**: Heuristic string matching in `core/causal_strategy_harness.py` replaced with explicit declarative metadata (`required_underlyings`, `required_feeds`) on `CANONICAL_STRATEGIES`. Result: `PASS`.
7. **Frozen Boundary**: Zero changes to frozen candidate specs, thresholds, signal logic, or risk boundaries. Result: `PASS`.
8. **CI Health Gates & Unit Tests**: All 4 primary test workflows passed in CI (100% of unit tests and health gates). Non-required Netlify preview failures documented.

## Safety Declaration
- read_only = true
- shadow_only = true
- broker_write_authority = false
- order_authority = false
- paper_authorized = false
- live_authorized = false
- orders_placed = 0
- orders_modified = 0
- orders_cancelled = 0
