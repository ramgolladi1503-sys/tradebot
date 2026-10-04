# Hermes contract — governed cash-observation token identity

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Keep MEG cash observations outside index-option resolution and preserve their identity
**scope:** In governed Market Event Graph (MEG) mode, restrict both depth builders to the configured index option products and retain successfully merged registry observation tokens as cash/underlying identities.
**requested_paths:** `core/depth_subscription_engine.py`, `core/kite_depth_ws.py`, `tests/test_depth_subscription_tokens.py`, `tests/test_subscription_universe_123_contract.py`
**allowed_paths:** requested source/tests, this contract, the matching GSD plan, the required PR review, and directly relevant evidence.
**forbidden_paths:** changing the existing governed MEG budget, option resolver behavior beyond filtering its MEG input symbols, freshness/recovery changes, risk/kill-switch changes, broker/order calls, credentials, live-mode changes, production-data mutation, and unrelated paths.
**expected_tests:** both builders exclude MEG cash constituent symbols from option resolution; successful registry merges add only active registry tokens to all underlying identity maps; failed merges do not publish constituent identity; a higher general depth budget is capped at 123 in MEG mode; production option counts and existing safety boundaries remain intact.
**acceptance_proof:** offline deterministic tests use a synthetic verified registry and mocked option resolver, assert exact 123-token union and resolver inputs in both builders, and exercise a blocked merge. No broker or live process is used.

## Invariants

1. In MEG mode, only the configured index products (`NIFTY`, `BANKNIFTY`, `SENSEX`) enter option resolution. Constituent cash instruments are not derivative-chain requests.
2. The validated observation registry is the sole source for observation token-to-symbol identity. Tokens are classified only if present in both the successful final union and the registry token list.
3. Successful observation tokens are kept consistent across generic token-to-symbol and underlying identity maps. A failed merge adds none of the observation-only tokens to those maps.
4. The existing MEG budget remains capped at 123 even if the general depth budget is higher. Per-symbol option counts, transport/recovery, feed freshness, execution authority, and mode boundaries do not change.
5. No live execution or broker authority is added.

## Failure behavior

An unsuccessful merge remains blocked by the existing subscription plan. The builder must not partially claim constituent identities. Invalid/unavailable registry input remains on the existing fail-closed path.

## Rollback and rollout

Revert the two builder changes and regression tests. There is no config migration. After merge, use separately authorized read-only observation to compare actual token identity against the canonical registry; offline tests do not establish live delivery or readiness.
