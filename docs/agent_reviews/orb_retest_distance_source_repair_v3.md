# ORB Retest Distance Source Repair v3

mode: PAPER
candidate_id: orb_retest_distance_source_repair_v3_pr682
decision: documentation_evidence_gate_repair
reason: Added required agent-review and CE evidence fields for the approved ORB source-ownership repair without changing ORB production semantics.
timestamp: 2026-07-20T18:35:00Z
is_order_action: false
broker_api_called: false
source: docs.agent_reviews.orb_retest_distance_source_repair_v3

Verified baseline: `a48176fc245375f15e316493364915ec37439e29`

## Agent Work Contract

Audited baseline: `a48176fc245375f15e316493364915ec37439e29`.

Strategy lane objective: correct ORB retest-distance source ownership so `retest_distance_pct` is calculated from `setup.retest_bar.close` to `setup.normalized_boundary_value`.

Approved files for this lane: `strategies/movement/opening_range_breakout.py`, `tests/test_opening_range_retest_temporal_fixture_contract.py`, and this review evidence file.

Prohibited changes: temporal predicates, thresholds, strategy identity, execution authority, risk handling, ranking behavior, broker integration, configuration, Trend Pullback, and Compression Breakout.

Acceptance requirement: evidence-first proof from tests, formula oracle, diff review, compile, Ruff, and checksum-preserving integration evidence.

No threshold tuning was performed. No profitability-driven repair was performed.

## Scope Guard

Allowed scope: retest-distance source correction and truthful evidence fields for ORB.

Prohibited scope: temporal candidate predicates, temporal sequencing, thresholds, strategy identity, execution, risk, ranking, feed gates, broker operations, and unrelated cleanup.

The repair changed ownership of `retest_distance_pct` only. `breakout_distance_pct` remains independently owned by `setup.breakout_bar.close`.

## High-Risk Path Review

`strategies/` is high-risk because strategy output can influence downstream candidate selection and, if later promoted by separate owners, execution-adjacent decisions. This PR does not add execution authority.

High-risk review findings:

- `retest_distance_pct` changed from breakout-bar close ownership to retest-bar close ownership.
- `breakout_distance_pct` remains owned by breakout-bar close.
- Temporal candidate presence is unchanged.
- Threshold values are unchanged.
- Strategy identity is unchanged.
- No execution, risk, feed, broker, or ranking authority was added.

## Grill Me Review

Question: Could ORB have accidentally changed candidate timing?

Answer: The diff review found no changes to temporal predicate functions or temporal thresholds. The ORB lane test result was `46 passed`, and the focused integration suite result was `86 passed`.

Question: Could the repair have changed thresholds instead of fixing source ownership?

Answer: The scope diff and tests show the approved change is the source for `retest_distance_pct`; threshold/profile values are recorded as unchanged.

Question: Could the new evidence be consumed as execution truth?

Answer: The branch adds evidence fields only. A scoped production search found no execution, risk, or ranking consumer interpreting ORB evidence `spot_ltp` as current live spot.

Review status: acceptable for continued CI validation.

## Hermes Review

The design keeps distance ownership deterministic: retest distance is sourced from `retest_bar.close`; breakout distance is sourced from `breakout_bar.close`.

Source commit provenance is preserved through the v2 contract bundle at `02ed107c14617f6f31c39e832553895ce07dce24`. Git-blob verification confirmed that the ORB source hash in the v2 bundle matches that commit and the current repaired source.

The corrected v2 bundle hash is `14f80680534e4216255569eadb8fb55b86be2c04298eb22810820498efd182e0`, and the sidecar verifies with `shasum -a 256 -c`.

The v1 historical bundle remains separate from current v2 source identity. No ambiguous or fabricated provenance is used.

## GSD Review

This is the smallest viable ORB repair: one source-owner correction, focused fixture coverage, explicit evidence fields, and no generalized framework.

The implementation avoids architecture changes, threshold redesign, strategy switching, execution wiring, and unrelated cleanup.

## QA / Safety Review

Recorded validation:

- Focused suite: `86 passed`.
- ORB lane: `46 passed`.
- Legacy opening-movement file after stale oracle repair: `8 passed`.
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

GitHub CI exposed one stale pre-repair score expectation in
`tests/test_opening_movement_strategies.py::test_orb_retest_generates_valid_call_candidate_near_retest_level`.
The focused 86-test suite did not include that legacy opening-movement test.
The expectation was updated only after an independent fixture calculation
matched the repaired implementation output. Production code, thresholds, and
temporal predicates remained unchanged.

## Acceptance Proof

Commands and results:

```bash
pytest -q tests/test_opening_movement_strategies.py::test_orb_retest_generates_valid_call_candidate_near_retest_level -vv
# Result: 1 passed

pytest -q tests/test_opening_movement_strategies.py
# Result: 8 passed

pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py
# Result: 46 passed

PYTHONPATH=. /opt/anaconda3/bin/python3.12 -m pytest -q -o addopts='' -m "not integration and not feed_smoke and not feed_soak and not certification" --durations=25
# Result: 6329 passed, 1 skipped, 24 deselected

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

Independent ORB formula oracle result:

```text
CALL retest_distance_pct=0.0 breakout_distance_pct=0.0035398230088495575
PUT retest_distance_pct=0.0 breakout_distance_pct=0.0035555555555555557
ORB_INDEPENDENT_FORMULA_ORACLE=PASS
```

Legacy opening-movement fixture oracle:

```text
CALL boundary=22600.0 breakout_close=22608.0 retest_close=22600.0 continuation_close=22614.0 expected_retest_distance=0.0 actual_retest_distance=0.0 expected_breakout_distance=0.00035398230088495576 actual_breakout_distance=0.00035398230088495576 independently_expected_raw_score=0.51 actual_raw_score=0.51 result=PASS
PUT boundary=22500.0 breakout_close=22492.0 retest_close=22498.0 continuation_close=22484.0 expected_retest_distance=8.888888888888889e-05 actual_retest_distance=8.888888888888889e-05 expected_breakout_distance=0.00035555555555555557 actual_breakout_distance=0.00035555555555555557 independently_expected_raw_score=0.4877777777777778 actual_raw_score=0.4877777777777778 result=PASS
```

Changed-file scope command:

```bash
git diff --name-status a48176fc245375f15e316493364915ec37439e29..HEAD
# Result: changed files limited to approved ORB/VWAP strategy repairs, tests, bundles, and review evidence.
```

ORB `spot_ltp` downstream-consumer search:

```bash
git grep -n -E "\\[['\"]spot_ltp['\"]\\]|\\.get\\(['\"]spot_ltp['\"]\\)|evidence.*spot_ltp|spot_ltp.*evidence" -- core strategies scripts '*.py' ':!runtime/*' ':!docs/*' ':!tests/*'
# Result: only core/runtime_snapshot_producer.py writes StrategyContext spot_ltp from market data; no ORB evidence execution/risk/ranking consumer found.
```

## Runtime Proof Required After Merge

This PR does not establish live readiness.

Post-merge proof still required before live use:

- Paper/shadow runtime only.
- Candidate generation remains non-executable until downstream owners approve it.
- ORB evidence fields remain evidence rather than execution truth.
- No rejected or fallback data becomes execution-eligible.
- No broker order is permitted as part of this proof.

This proof has not occurred in this PR.

Edge validation remains a separate pre-merge task against the unmerged PR 682
head.

## What This PR Does Not Prove

This PR does not prove profitability, structural edge, WFA success, live readiness, production certification, execution authority, capital allocation quality, Trend Pullback correctness, or Compression Breakout correctness.

## Human Approval

The human-approved ORB scope was limited to the mathematical source-ownership correction.

V1 remains historical. V2 owns current repaired source identity. PR 682 remains draft. Merging requires separate explicit human approval after all CI checks pass.
