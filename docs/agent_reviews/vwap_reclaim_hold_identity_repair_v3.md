# VWAP Reclaim-Hold Identity Repair v3

mode: PAPER
candidate_id: vwap_reclaim_hold_identity_repair_v3_pr682
decision: documentation_evidence_gate_repair
reason: Added required agent-review and CE evidence fields for the approved VWAP behavioral-identity repair without changing VWAP production semantics.
timestamp: 2026-07-20T18:35:00Z
is_order_action: false
broker_api_called: false
source: docs.agent_reviews.vwap_reclaim_hold_identity_repair_v3

Verified baseline: `a48176fc245375f15e316493364915ec37439e29`

## Agent Work Contract

Audited baseline: `a48176fc245375f15e316493364915ec37439e29`.

Strategy lane objective: correct VWAP behavioral wording to match implemented reclaim-and-hold behavior while preserving compatibility identifiers.

Approved files for this lane: `strategies/movement/vwap_reclaim.py`, `tests/test_vwap_trap_movement_strategies.py`, `tests/vwap_reclaim_test_support.py`, and this review evidence file.

Prohibited changes: predicates, score formula, thresholds, compatibility IDs, rejection-pattern implementation, execution authority, risk handling, ranking behavior, broker integration, configuration, Trend Pullback, and Compression Breakout.

Acceptance requirement: evidence-first proof from tests, stale-label search, diff review, compile, Ruff, and versioned contract evidence.

No threshold tuning was performed. No profitability-driven repair was performed.

## Scope Guard

Allowed scope: behavioral wording correction from reclaim-or-rejection phrasing to reclaim-and-hold phrasing.

Prohibited scope: predicate changes, score changes, threshold changes, compatibility-ID changes, rejection-pattern additions, execution, risk, ranking, feed gates, broker operations, and unrelated cleanup.

Compatibility identifiers remain `vwap_reclaim_rejection_v1`, `VWAP_RECLAIM_REJECTION`, and `vwap_reclaim_causal_v1`.

## High-Risk Path Review

`strategies/` is high-risk because strategy output can influence downstream candidate selection and, if later promoted by separate owners, execution-adjacent decisions. This PR does not add execution authority.

High-risk review findings:

- Active behavior is reclaim-and-hold.
- Only behavioral labels changed.
- Predicate logic is unchanged.
- Score logic is unchanged.
- Threshold values are unchanged.
- Compatibility identifiers are unchanged.
- No rejection predicate was added.
- No execution, risk, feed, broker, or ranking authority was added.

## Grill Me Review

Question: Could the VWAP rename have changed acceptance behavior?

Answer: The diff review found no changes to `_sequence_matches`, score construction, CHOP gate, minimum VWAP distance gate, or maximum entry-distance gate. The VWAP lane test result was `11 passed`, and the focused integration suite result was `86 passed`.

Question: Could downstream code still consume stale behavior labels?

Answer: The scoped stale-label search found compatibility IDs and generator names only. It did not find active production consumers of the old behavior labels.

Question: Could a rejection strategy have been introduced under the compatibility ID?

Answer: The implementation records `implemented_pattern = VWAP_RECLAIM_HOLD`, and tests assert no predicate, score, threshold, or compatibility-ID change.

Review status: acceptable for continued CI validation.

## Hermes Review

The design separates behavioral identity from compatibility identity. Current behavior is `VWAP_RECLAIM_HOLD`; compatibility IDs remain stable for downstream registries.

Source commit provenance is preserved through the v2 contract bundle at `02ed107c14617f6f31c39e832553895ce07dce24`. Git-blob verification confirmed that the VWAP source hash in the v2 bundle matches that commit and the current repaired source.

The corrected v2 bundle hash is `14f80680534e4216255569eadb8fb55b86be2c04298eb22810820498efd182e0`, and the sidecar verifies with `shasum -a 256 -c`.

The v1 historical bundle remains separate from current v2 source identity. No ambiguous or fabricated provenance is used.

## GSD Review

This is the smallest viable VWAP repair: one terminology correction, focused tests and support updates, explicit compatibility evidence, and no generalized framework.

The implementation avoids architecture changes, threshold redesign, strategy switching, execution wiring, and unrelated cleanup.

## QA / Safety Review

Recorded validation:

- Focused suite: `86 passed`.
- VWAP lane: `11 passed`.
- Compile: passed.
- Ruff: passed.
- Diff check: passed.
- Sidecar check: passed.
- Broker call: none.
- Order action: none.
- Live configuration change: none.
- Risk/feed gate change: none.
- New configuration keys: none.

Full GitHub CI success is not claimed until all checks complete successfully.

## Acceptance Proof

Commands and results:

```bash
pytest -q tests/test_vwap_trap_movement_strategies.py
# Result: 11 passed

pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_contract_v2.py tests/test_strategy_parameter_profiles.py tests/test_movement_regime.py
# Result: 86 passed

python3 -m py_compile strategies/movement/opening_range_breakout.py strategies/movement/vwap_reclaim.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_contract_v2.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
# Result: PASS

ruff check strategies/movement/opening_range_breakout.py strategies/movement/vwap_reclaim.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_contract_v2.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
# Result: PASS

git diff --check
# Result: PASS

shasum -a 256 docs/agent_reviews/four_strategy_contract_bundle_v1.json docs/agent_reviews/four_strategy_contract_bundle_v2.json
# Result: 8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2  docs/agent_reviews/four_strategy_contract_bundle_v1.json
# Result: 14f80680534e4216255569eadb8fb55b86be2c04298eb22810820498efd182e0  docs/agent_reviews/four_strategy_contract_bundle_v2.json

shasum -a 256 -c docs/agent_reviews/four_strategy_contract_bundle_v2.json.sha256
# Result: docs/agent_reviews/four_strategy_contract_bundle_v2.json: OK
```

VWAP stale-label search:

```bash
git grep -n -E "confirmed_vwap_reclaim_or_rejection|upside_vwap_reclaim_or_rejection|downside_vwap_reclaim_or_rejection|reclaim_rejection" -- core strategies scripts config '*.py' '*.yml' ':!docs/*' ':!runtime/*' ':!tests/*'
# Result: compatibility IDs and generator names only; no active production stale behavior-label consumer found.
```

Changed-file scope command:

```bash
git diff --name-status a48176fc245375f15e316493364915ec37439e29..HEAD
# Result: changed files limited to approved ORB/VWAP strategy repairs, tests, bundles, and review evidence.
```

## Runtime Proof Required After Merge

This PR does not establish live readiness.

Post-merge proof still required before live use:

- Paper/shadow runtime only.
- Candidate generation remains non-executable until downstream owners approve it.
- VWAP reclaim-and-hold labels appear consistently.
- No rejected or fallback data becomes execution-eligible.
- No broker order is permitted as part of this proof.

This proof has not occurred in this PR.

## What This PR Does Not Prove

This PR does not prove profitability, structural edge, WFA success, live readiness, production certification, execution authority, capital allocation quality, Trend Pullback correctness, or Compression Breakout correctness.

## Human Approval

The human-approved VWAP scope was limited to the behavioral-identity correction.

V1 remains historical. V2 owns current repaired source identity. PR 682 remains draft. Merging requires separate explicit human approval after all CI checks pass.
