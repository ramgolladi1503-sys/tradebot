# Hermes contract — observation-token identity classification

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Preserve cash identity for merged market-observation tokens
**scope:** In governed MEG mode, restrict option resolution to configured index products and classify tokens from the verified observation registry as cash/underlying identities after a successful subscription merge in both subscription-builder paths.
**requested_paths:** `core/depth_subscription_engine.py`, `core/kite_depth_ws.py`, `tests/test_depth_subscription_tokens.py`
**allowed_paths:** requested source and test paths, this contract, the matching GSD plan, and Issues 7–11 evidence artifacts.
**forbidden_paths:** broker/order calls, credentials, risk or kill-switch changes, token-budget changes, option-resolution changes, feed-freshness changes, live-mode changes, live process access, and unrelated paths.
**expected_tests:** constituent symbols never enter option resolution in either builder; observation tokens become underlying identities only after a successful merge; token-to-symbol mappings match the verified registry; blocked merges do not acquire observation identity; existing 123-token topology and option counts remain unchanged.
**acceptance_proof:** focused subscription tests exercise both builders with a synthetic verified registry and mocked option resolver; they assert identity maps, option-resolution inputs, and exact unchanged subscription membership. No broker or live runtime is used.

## Invariants

1. The verified observation registry is the authority for observation-token identity. Only its `token_by_symbol` entries may be added as observation cash identities.
2. In governed MEG mode, option-resolution inputs are restricted to the configured index product set. Cash constituent symbols must never be expanded into derivative option chains.
3. Identity classification happens only after the subscription merge reports success. A blocked merge must not make omitted observation tokens appear active or owned.
4. Every merged observation token is represented consistently in the token-to-symbol map, underlying-token set, and underlying-token-to-symbol map. Existing production index-underlying identity remains valid when it overlaps the observation registry.
5. Observation constituents remain outside option-chain resolution. The 123-token topology, production option counts, subscription budget, and freshness/recovery policy remain unchanged.
6. This change supplies identity metadata only; it grants no execution, order, broker, paper, or live authority.

## Failure handling

An invalid or unsuccessful observation merge remains governed by the existing blocked-plan path. The implementation must not partially classify or publish observation tokens on that path. Registry validation and budget enforcement remain upstream authorities and are not weakened here.

## Rollback

Revert the identity-map additions and their tests. This returns the existing ambiguous token classification; it does not require a schema migration or config change.

## Runtime-proof boundary

Offline tests prove builder behavior only. After merge, read-only observation evidence must separately confirm the actual registry identity, subscribed-token map, and observed cash-token classification. This contract authorizes no live run.
