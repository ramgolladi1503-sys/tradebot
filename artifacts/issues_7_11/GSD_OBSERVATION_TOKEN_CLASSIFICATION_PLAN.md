# GSD execution — observation-token identity classification

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Keep verified cash observations out of option identity classification
**scope:** Apply the Hermes contract to the direct and installed depth subscription builders.
**requested_paths:** `core/depth_subscription_engine.py`, `core/kite_depth_ws.py`, `tests/test_depth_subscription_tokens.py`
**allowed_paths:** requested source and test paths, this plan, the matching Hermes contract, and Issues 7–11 evidence artifacts.
**forbidden_paths:** broker/order calls, credentials, risk or kill-switch changes, token-budget changes, option-resolution changes, feed-freshness changes, live-mode changes, live process access, and unrelated paths.
**expected_tests:** both builder paths classify successful observation tokens consistently; failed merges do not classify them; constituents remain excluded from option resolution; exact subscription membership and option counts remain stable.
**acceptance_proof:** focused deterministic tests with a synthetic registry and mocked resolver, plus diff/scope inspection. No live or broker operations.

## Execution steps

1. Restrict both builders to configured index product symbols when governed MEG mode is active.
2. Add observation identity entries to all underlying-identity maps only in the successful merge branch of each builder.
3. Add assertions for observation identities and unchanged option-resolution input in focused tests.
4. Add a failed-merge assertion if the existing test fixtures can drive the existing blocked branch without changing production behavior.
5. Run the focused subscription tests and relevant safety/contract checks; retain results against the exact commit.
6. Confirm no token budget, feed gate, or execution boundary changed.

## Risks and limits

Misclassifying a derivative token as cash could distort feed/depth accounting. The registry is the sole identity source, and tests will use known cash tokens and explicit options to prove disjointness. These tests do not establish live subscription delivery or provider behavior.

## Rollout

No configuration key or migration is required. After merge, perform only separately authorized read-only runtime observation and verify cash-token identity against the canonical registry. Do not infer live readiness from offline builder tests.

## Execution result — 2026-10-04

- Focused command: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_depth_subscription_tokens.py tests/test_depth_subscription_refresh_contract.py` → **20 passed**.
- The regression exercises both the WebSocket builder and the direct depth engine with 50 extra cash symbols. Both produce the exact 123-token union, resolve options only for NIFTY/BANKNIFTY/SENSEX, and map verified observation tokens to underlying identity.
- The blocked-merge mutation fixture confirms constituent identities are not added to active underlying or symbol maps.
- `git diff --check` passed. Hosted exact-head CI remains required; no live runtime evidence is claimed.
