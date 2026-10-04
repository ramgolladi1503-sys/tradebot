# Issues 7-11 baseline

- Repository SHA: `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
- Branch/worktree: `ram/issues-7-11-graph-repair` / `/Users/madhuram/.codex/worktrees/pr955-batch-bound/tradebot`
- Canonical checkout was dirty and remains untouched. Campaign work is an uncommitted diff in the isolated worktree.
- Original advisory/telemetry baseline: 48 passed, 1 warning; earlier Issue 10 patch baseline: 53 passed, 1 warning.
- Continuation preflight on 2026-10-03: isolated worktree `/Users/madhuram/.codex/worktrees/pr955-batch-bound/tradebot`, branch `ram/issues-7-11-graph-repair`, base HEAD `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`; pre-existing dirty in-scope campaign diff preserved. Canonical checkout remains separate and untouched. No active pytest process was found at continuation start.
- Current focused Issue 9 quote-time/fetch-path suite: 125 passed, 1 warning; the newly added normal C1 restart integration passed separately (1 passed, 1 warning).
- Current combined Issues 7–11 heritage/store/feed/token/advisory suites: 368 passed, 1 skipped, 1 warning in 16.88s.
- Adjacent feed/subscription/token/depth suites: 252 passed, 1 warning; token coverage/dynamic budget check: 5 passed, 1 warning.
- `PYTHONPATH=. python3 scripts/certify_market_session_memory.py`: 10/10 gates PASS. Output: `evidence/market_session_memory_v1/certification.json`.
- Latest broad regression on the post-Hermes-scope-correction source: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py --ignore=tests/trade_truth/test_raw_tick_expected_separation.py -k 'not test_v5_verifier_deep_primitive_validation'` → 8608 passed, 9 skipped, 29 deselected, 1474 warnings in 667.63s. Full collection without exclusions remains unavailable because `upstox_client` is missing; excluded capture-backed tests remain unverified.
- Scoped Issues 1–6 preservation suite: 221 passed, 1 warning in 24.16s; limitations are listed in `ISSUES_1_6_PROTECTION.md`.
- Offline tests are not live proof.
