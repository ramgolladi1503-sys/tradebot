# Differential regression

- Repository HEAD before this campaign's uncommitted work and current HEAD are both `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`; tracked source changes are confined to the file list in the worktree diff.
- Focused Issue 9 quote/time path suite after REST-depth LTP integration attack: 125 passed, 1 existing Hypothesis `.hypothesis` ignore warning.
- Cross-issue/heritage/store/feed/token/advisory regression on current diff: 368 passed, 1 skipped, 1 warning in 16.88s. Command is recorded in `REPAIR_LEDGER.md`.
- Normal primary-runtime path now has one explicit restart integration test: `trusted source-time tick → singleton buffer → durable completed bar → process-local state clear → exact restore → C1 durable-memory read` passed. Current-cycle freshness remained separately required.
- A second independent event-time attack found the read-only observer used quote-book time to grade LTP freshness. The observer now consumes `last_price_ts_epoch` only, rejects missing/future time as unknown, and fixes `is_executable_quote=false`. The runtime-composition regression passes with a current book and stale trade event.
- Adjacent PR feed, subscription, token, and depth suite: 252 passed, 1 same warning.
- Token coverage and dynamic subscription-budget checks: 5 passed, 1 same warning.
- Market Session Memory certification: 10/10 gates PASS; evidence at `evidence/market_session_memory_v1/certification.json`.
- Candidate dependency source digest was refreshed for the exact modified MarketSessionStore bytes. `tests/test_edge43_feed_health_truth.py` and `tests/test_edge45_symbol_execution_safety.py` pass; unknown/partial candidate authority still blocks execution.
- One combined run initially exposed a test-state leak (observer singleton store left bound by another test); the packet proof now explicitly clears that fixture state, after which the full focused suite passed. No production assertion was weakened.
- No changes to strategy thresholds, candidate ranking, risk limits, broker/order code, credential/environment files, or configured token universe. `git diff` confirms no config or strategy files changed.
- Final integrated repository test run on current source, excluding only unavailable Upstox integration module: 8571 passed, 9 skipped, 28 deselected, 1474 warnings in 923.50 seconds, using a temporary `python` alias to installed `python3`. This is local test evidence, not remote CI.
- Captured Issues 1–6 exact regression group and before/after token-universe artifact comparison were not run. Required A–F composed scenarios, targeted campaign code-mutation harness, and independent second-context verifier remain open. No whole-campaign regression certification claim.
- The attempted current-source broad suite was stopped at 28% when the event-time verifier found the observer freshness defect. It is recorded as interrupted and must not be counted as pass; rerun the documented broad command after the targeted repairs stabilize.
