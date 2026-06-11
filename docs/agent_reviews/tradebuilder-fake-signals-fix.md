# Agent Review Evidence: TradeBuilder Fake Signals Fix

## Agent Work Contract
- **Source Agent:** GSD
- **Action:** Fix Phase 2 strict mode leak caused by softened candidates.
- **Title:** Fix fake fallback signals leaking into Phase 2 strict mode.
- **Scope:** Wrapping `TradeBuilder._soften_reject_to_candidate` calls in `allow_fallbacks` checks, and fixing feed SLA tests that read state from disk.
- **Requested Paths:** `strategies/trade_builder.py`, `tests/test_trade_builder_soft_vetoes.py`, `tests/test_feed_health_epoch_missing.py`, `tests/test_freshness_sla_stale_token_ratio.py`, `tests/test_feed_freshness_units.py`
- **Allowed Paths:** Same as requested paths.
- **Forbidden Paths:** Core risk, core auth, `core/execution/`, `main.py`
- **Expected Tests:** Feed health tests must not read `runtime_snapshot.json` from previous live runs on disk. Trade builder tests must assert softened fallbacks are not emitted in strict mode.
- **Acceptance Proof:** 100% pass on pytest for `test_trade_builder_soft_vetoes.py` and the modified feed SLA test suites.

## Scope Guard
The scope is purely fixing the TradeBuilder fallback leak and fixing dirty state leaks in 3 SLA test files. No changes to actual phase 2 bounds, no execution logic changes, no risk parameter modifications.

## Grill Me Review
- Did we change risk thresholds? No.
- Did we add new fallback paths? No, we restricted existing fallback paths so they don't fire when `allow_fallbacks=False`.
- Does this solve the *entire* ranking fake signal problem? No, it solves the origin leak at the TradeBuilder level for strict mode. A follow-up is needed to quarantine soft signals at the Phase 2, Ranking, and UI boundaries.

## Hermes Review
Architecture aligns with existing design. `allow_fallbacks` parameter in `trade_builder.py` is now fully respected across all drop points in `build()`.

## GSD Review
- Replaced rogue fallback calls with `if allow_fallbacks:` checks.
- Set `FEED_FRESHNESS_RUNTIME_SNAPSHOT_ENABLE = False` in feed tests to isolate them from dirty disk state.

## QA / Safety Review
- All 74 TradeBuilder soft veto tests pass.
- Feed SLA tests pass and are robust against local disk pollution.
- No `LIVE` paths were modified.
- High-Risk Path Review: Checked that TradeBuilder does not emit executable signals from these fallbacks. The generated fallbacks were always `execution_allowed=False` anyway, but now they are fully blocked when `allow_fallbacks=False`. This makes Phase 2 safer.

## Acceptance Proof
```bash
pytest -q tests/test_trade_builder_soft_vetoes.py
........................................................................ [ 97%]
..                                                                       [100%]
74 passed in 7.12s
```
```bash
pytest -q tests/test_feed_health_epoch_missing.py tests/test_freshness_sla_stale_token_ratio.py tests/test_feed_freshness_units.py
.....                                                                    [100%]
5 passed in 1.45s
```

## Runtime Proof Required After Merge
None, because this is purely tightening strict mode constraints. However, running a SIM day and verifying the dashboard does not show advisory-only trades leaking into top ranked opportunities is recommended.

## What This PR Does Not Prove
This PR does not prove that Phase 2, ranking, and UI payload boundaries are structurally immune to advisory candidates if one happens to leak through in the future. Follow-up PRs must add explicit boundary quarantines for `planning_only` or `execution_allowed=False` rows.

## Human Approval
The USER explicitly commanded: "Create a PR for this fix now".

## High-Risk Path Review
`strategies/trade_builder.py` is a high risk file. The modifications strictly enforce the `allow_fallbacks` parameter constraint that was being bypassed. No execution or risk limits were loosened.
