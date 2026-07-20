# Four Strategy Objective Math Repairs v3

mode: PAPER
candidate_id: four_strategy_objective_math_repairs_v3_pr682
decision: documentation_evidence_gate_repair
reason: Added required agent-review and CE evidence fields for PR 682 without production, test, bundle, sidecar, risk, feed, broker, or execution changes.
timestamp: 2026-07-20T18:35:00Z
is_order_action: false
broker_api_called: false
source: docs.agent_reviews.four_strategy_objective_math_repairs_v3

Audited baseline: `a48176fc245375f15e316493364915ec37439e29`

Integration source commit before bundle/evidence maintenance: `02ed107c14617f6f31c39e832553895ce07dce24`

## Audit Artifact Hashes

```text
4694a2a40ce4e53ce868ff44b952c4aa8721e4fe5525ded0bcca2f84331a1fc4  objective_repairs_v2.json
a606b482154f9672f87fb72e0f713f734935ac4f5cee11aae40e45cfa757385a  design_decisions_required_v2.json
e486a6ffff53fa60d0fc610dff0691955fc211dd446c7b7348cd5937315c58f3  authority_register_v2.json
6099b1ed4d114b81cb7d26a5f3063e5a9baa506b7560fcfeb44599ef9da42cf0  four_strategy_authoritative_math_audit_v2.json
2d86e12ee2bd295320c7dfa40317eb536a4d9a0f3d05201f6c554a7b04d268a3  opening-range-retest/audit.json
6e024457a6efc62a34f3ee75f3b5ec953e81b35e9da3712bf335f271e63dac58  vwap-reclaim/audit.json
dbe8365c9b9c1f59d3ce37e33b58ad77f9f489e39ac53dbb65571b4610bf0de9  baseline_reconciliation.json
```

## Approved Human Decisions

ORB: `retest_distance_pct` must be calculated from `setup.retest_bar.close` to `setup.normalized_boundary_value`. `breakout_distance_pct` remains independently calculated from `setup.breakout_bar.close`.

VWAP: implemented behavior is `VWAP_RECLAIM_HOLD`. No rejection predicate is added. Compatibility identifiers `vwap_reclaim_rejection_v1` and `VWAP_RECLAIM_REJECTION` are preserved.

## ORB Repair

Before:

```text
retest_distance_pct = abs(setup.breakout_bar.close - setup.normalized_boundary_value) / abs(setup.normalized_boundary_value)
```

After:

```text
retest_distance_pct = abs(setup.retest_bar.close - setup.normalized_boundary_value) / abs(setup.normalized_boundary_value)
breakout_distance_pct = directional_distance(setup.breakout_bar.close, setup.normalized_boundary_value)
```

Temporal candidate presence changed: `NO`

Threshold/profile values changed: `NO`

Evidence changed: added `breakout_close`, `retest_close`, `continuation_close`, `retest_distance_source`, and `breakout_distance_source`.

Fingerprint impact: approved ORB raw-score fingerprint changes from `0.42150442477876104` in v1 bundle evidence to `0.54` in v2 bundle evidence.

Lane commit: `b2439e50565406bbf9910897294d23e67e7c307a`

## VWAP Repair

Before:

```text
confirmed_vwap_reclaim_or_rejection
confirmed VWAP reclaim/rejection in a non-chop regime
reclaim_rejection
```

After:

```text
confirmed_vwap_reclaim_hold
confirmed VWAP reclaim and hold in a non-chop regime
reclaim_hold
```

Predicate changed: `NO`

Score changed: `NO`

Rejection predicate added: `NO`

Threshold/profile values changed: `NO`

Fingerprint impact: approved `entry_trigger` and `rank_reason` text changed; raw score remains `0.392377`.

Lane commit: `1e39022558d5c2ed6d864d37a94db4b04236f7cc`

## Contract Bundle Evidence

V1 bundle byte-preservation hash:

```text
8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2  docs/agent_reviews/four_strategy_contract_bundle_v1.json
```

V2 bundle hash:

```text
14f80680534e4216255569eadb8fb55b86be2c04298eb22810820498efd182e0  docs/agent_reviews/four_strategy_contract_bundle_v2.json
3fdd138de5c4dfc0e7cfafa2503e68002525b7a8534b30d59e7b678fe17c5c8d  docs/agent_reviews/four_strategy_contract_bundle_v2.json.sha256
```

V2 bundle source commit uses the pre-bundle integration content identity `02ed107c14617f6f31c39e832553895ce07dce24`, because the final integration commit includes evidence and contract files rather than additional production source edits. The earlier invalid full SHA `02ed107c9f6253736ea8ac564961e5121d77be42` was rejected because it was not a Git commit object; Git-blob provenance was independently verified against the corrected commit.


## Historical Freeze Policy

The v1 bundle remained byte-identical. The v1 freeze test validates historical bundle bytes, source commit, stored hashes, strategy records, and fingerprints, but no longer compares historical v1 hashes to current repaired source files. Historical v1 source hashes were independently verified against Git blobs from the recorded v1 source commit `94b48666d166c45e4b65679b4811aa1ddc237b46`. Current ORB/VWAP source identity is verified by the corrected v2 bundle at source commit `02ed107c14617f6f31c39e832553895ce07dce24`.

## Validation

ORB lane:

```text
pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py
python3 -m py_compile strategies/movement/opening_range_breakout.py tests/test_opening_range_retest_temporal_fixture_contract.py
ruff check strategies/movement/opening_range_breakout.py tests/test_opening_range_retest_temporal_fixture_contract.py
git diff --check
Result: PASS, 46 passed
```

VWAP lane:

```text
pytest -q tests/test_vwap_trap_movement_strategies.py
python3 -m py_compile strategies/movement/vwap_reclaim.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
ruff check strategies/movement/vwap_reclaim.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
git diff --check
Result: PASS, 11 passed
```

Integration:

```text
pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_contract_v2.py tests/test_strategy_parameter_profiles.py tests/test_movement_regime.py
python3 -m py_compile strategies/movement/opening_range_breakout.py strategies/movement/vwap_reclaim.py tests/test_four_strategy_contract_v2.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
ruff check strategies/movement/opening_range_breakout.py strategies/movement/vwap_reclaim.py tests/test_four_strategy_contract_v2.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
git diff --check
Result: PASS, 86 passed
```

## Scope Proof

Trend modified: `NO`

Compression modified: `NO`

Profile values changed: `NO`

Architecture added: `NO`

Design decisions beyond approval: `NO`

Broker API called: `NO`

Order action performed: `NO`

Backtest performed: `NO`

Forward returns calculated: `NO`

Pushed: `YES`

Draft PR created: `YES`

PR number: `682`

PR URL: `https://github.com/ramgolladi1503-sys/tradebot/pull/682`

Merged: `NO`

Documentation repair commit: final SHA recorded in PR 682 and final publication-gate evidence after commit creation.

Shared checkout `/Users/madhuram/tradebot` remained untouched and dirty with pre-existing changes.

## Agent Work Contract

Audited baseline: `a48176fc245375f15e316493364915ec37439e29`.

Integration lane objective: combine the approved ORB retest-distance source correction and approved VWAP behavioral-identity correction while maintaining versioned contract evidence.

Approved files: ORB/VWAP repaired strategy files, focused tests, v2 contract bundle and sidecar, and review evidence under `docs/agent_reviews/`.

Prohibited changes: Trend Pullback, Compression Breakout, architecture, configuration, feeds, execution, risk, broker integration, strategy threshold tuning, profitability-driven edits, and unrelated cleanup.

Acceptance requirement: evidence-first validation from tests, source-blob provenance, bundle hashes, sidecar verification, stale-label searches, formula oracle, and CI evidence gate.

No threshold tuning was performed. No profitability-driven repair was performed.

## Scope Guard

Allowed scope: combine the approved ORB/VWAP repairs and maintain versioned contract evidence.

Prohibited scope: Trend, Compression, architecture, configuration, execution, risk, feeds, broker operations, live behavior, order behavior, strategy-threshold redesign, ranking behavior, and source changes outside the approved ORB/VWAP strategy files.

The v1 contract remains a historical snapshot. The v2 contract owns current repaired source identity.

## High-Risk Path Review

`strategies/` is high-risk because strategy output can influence downstream candidate generation and later execution-adjacent paths if separate owners promote it. This PR does not grant execution authority.

High-risk integration findings:

- ORB `retest_distance_pct` changed from breakout-bar close ownership to retest-bar close ownership.
- ORB `breakout_distance_pct` remains owned by breakout-bar close.
- ORB temporal candidate presence is unchanged.
- ORB thresholds are unchanged.
- VWAP active behavior is reclaim-and-hold.
- VWAP label text changed to match implemented behavior.
- VWAP predicate, score, thresholds, and compatibility identifiers are unchanged.
- No forbidden high-risk files beyond the approved ORB/VWAP strategy files changed.
- No core/config/risk/execution/feed changes were made.
- No live or order behavior changed.

## Grill Me Review

Question: Could ORB have accidentally changed candidate timing?

Answer: The ORB diff review found no temporal predicate or threshold changes. ORB lane validation recorded `46 passed`, and the focused suite recorded `86 passed`.

Question: Could the VWAP rename have changed acceptance behavior?

Answer: The VWAP diff review found no changes to sequence predicate, score, CHOP gate, VWAP distance gate, entry-distance gate, or compatibility IDs. VWAP lane validation recorded `11 passed`.

Question: Could the v1 historical contract have been rewritten?

Answer: The v1 bundle hash remains `8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2`. The freeze test preserves v1 bytes and historical records while v2 owns current repaired source identity.

Question: Could the v2 bundle point to a nonexistent commit?

Answer: The invalid SHA was replaced with existing commit `02ed107c14617f6f31c39e832553895ce07dce24`, and Git-blob checks matched every v2 source hash to that commit.

Question: Could new evidence be consumed as execution truth?

Answer: The scoped ORB `spot_ltp` search found no execution, risk, or ranking consumer of ORB evidence as live spot. Candidate generation remains non-executable until downstream owners separately approve it.

Review status: acceptable for continued CI validation.

## Hermes Review

The contract structure separates deterministic source ownership, source commit provenance, and bundle identity.

Source commit provenance:

```text
02ed107c14617f6f31c39e832553895ce07dce24
```

Git-blob verification confirmed v2 source hashes for `config/strategy_inventory.yml`, `core/movement_contract.py`, `core/strategy_parameter_profiles.py`, ORB, Trend, Compression, and VWAP.

Bundle hashes:

```text
8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2  docs/agent_reviews/four_strategy_contract_bundle_v1.json
14f80680534e4216255569eadb8fb55b86be2c04298eb22810820498efd182e0  docs/agent_reviews/four_strategy_contract_bundle_v2.json
```

The v2 sidecar verifies. The v1 historical snapshot is intentionally separate from v2 current-source identity. No ambiguous or fabricated provenance is used.

## GSD Review

This is the smallest viable integration repair:

- One ORB source-owner correction.
- One VWAP terminology correction.
- Focused tests and evidence.
- Versioned contract bundle.
- No architecture or generalized framework.
- No threshold redesign.
- No unrelated cleanup.

## QA / Safety Review

Recorded validation:

- Focused suite: `86 passed`.
- ORB lane: `46 passed`.
- Legacy opening-movement file after stale ORB score-oracle repair: `8 passed`.
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

GitHub CI exposed one stale legacy ORB raw-score expectation in
`tests/test_opening_movement_strategies.py::test_orb_retest_generates_valid_call_candidate_near_retest_level`.
The focused 86-test suite did not include that legacy opening-movement test.
The assertion was repaired only after independent fixture calculation matched
the implementation output. Production code, thresholds, profiles, temporal
predicates, bundles, and sidecars remained unchanged. PR 682 remains draft and
unmerged. Edge validation remains a separate pre-merge task.

## Acceptance Proof

Focused tests:

```bash
pytest -q tests/test_opening_movement_strategies.py::test_orb_retest_generates_valid_call_candidate_near_retest_level -vv
# Result: 1 passed

pytest -q tests/test_opening_movement_strategies.py
# Result: 8 passed

PYTHONPATH=. /opt/anaconda3/bin/python3.12 -m pytest -q -o addopts='' -m "not integration and not feed_smoke and not feed_soak and not certification" --durations=25
# Result: 6329 passed, 1 skipped, 24 deselected

pytest -q tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_contract_v2.py tests/test_strategy_parameter_profiles.py tests/test_movement_regime.py
# Result: 86 passed in 1.16s
```

Compile:

```bash
python3 -m py_compile strategies/movement/opening_range_breakout.py strategies/movement/vwap_reclaim.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_contract_v2.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
# Result: PASS
```

Ruff:

```bash
ruff check strategies/movement/opening_range_breakout.py strategies/movement/vwap_reclaim.py tests/test_four_strategy_contract_freeze.py tests/test_four_strategy_contract_v2.py tests/test_opening_range_retest_temporal_fixture_contract.py tests/test_vwap_trap_movement_strategies.py tests/vwap_reclaim_test_support.py
# Result: All checks passed
```

Diff check:

```bash
git diff --check
# Result: PASS
```

V1 and v2 bundle hashes:

```bash
shasum -a 256 docs/agent_reviews/four_strategy_contract_bundle_v1.json docs/agent_reviews/four_strategy_contract_bundle_v2.json
# Result: 8b7df7e030306b9699347f9b3ed1c421fd8dfc302c7902a178e8111cb177d8c2  docs/agent_reviews/four_strategy_contract_bundle_v1.json
# Result: 14f80680534e4216255569eadb8fb55b86be2c04298eb22810820498efd182e0  docs/agent_reviews/four_strategy_contract_bundle_v2.json
```

V2 sidecar verification:

```bash
shasum -a 256 -c docs/agent_reviews/four_strategy_contract_bundle_v2.json.sha256
# Result: docs/agent_reviews/four_strategy_contract_bundle_v2.json: OK
```

ORB formula oracle:

```text
CALL raw_score=0.8396681415929202 retest_distance_pct=0.0 expected_retest_distance_pct=0.0 breakout_distance_pct=0.0035398230088495575 expected_breakout_distance_pct=0.0035398230088495575
PUT raw_score=0.8413888888888889 retest_distance_pct=0.0 expected_retest_distance_pct=0.0 breakout_distance_pct=0.0035555555555555557 expected_breakout_distance_pct=0.0035555555555555557
ORB_INDEPENDENT_FORMULA_ORACLE=PASS
```

Legacy opening-movement fixture oracle:

```text
CALL boundary=22600.0 breakout_close=22608.0 retest_close=22600.0 continuation_close=22614.0 expected_retest_distance=0.0 actual_retest_distance=0.0 expected_breakout_distance=0.00035398230088495576 actual_breakout_distance=0.00035398230088495576 independently_expected_raw_score=0.51 actual_raw_score=0.51 result=PASS
PUT boundary=22500.0 breakout_close=22492.0 retest_close=22498.0 continuation_close=22484.0 expected_retest_distance=8.888888888888889e-05 actual_retest_distance=8.888888888888889e-05 expected_breakout_distance=0.00035555555555555557 actual_breakout_distance=0.00035555555555555557 independently_expected_raw_score=0.4877777777777778 actual_raw_score=0.4877777777777778 result=PASS
```

VWAP stale-label search:

```bash
git grep -n -E "confirmed_vwap_reclaim_or_rejection|upside_vwap_reclaim_or_rejection|downside_vwap_reclaim_or_rejection|reclaim_rejection" -- core strategies scripts config '*.py' '*.yml' ':!docs/*' ':!runtime/*' ':!tests/*'
# Result: compatibility IDs and generator names only; no active production stale behavior-label consumer found.
```

ORB `spot_ltp` downstream-consumer search:

```bash
git grep -n -E "\\[['\"]spot_ltp['\"]\\]|\\.get\\(['\"]spot_ltp['\"]\\)|evidence.*spot_ltp|spot_ltp.*evidence" -- core strategies scripts '*.py' ':!runtime/*' ':!docs/*' ':!tests/*'
# Result: only core/runtime_snapshot_producer.py writes StrategyContext spot_ltp from market data; no ORB evidence execution/risk/ranking consumer found.
```

Changed-file scope:

```bash
git diff --name-status a48176fc245375f15e316493364915ec37439e29..HEAD
# Result: changed files limited to approved ORB/VWAP strategy repairs, tests, bundles, and review evidence.
```

## Runtime Proof Required After Merge

This PR does not establish live readiness.

Post-merge proof still required before live use:

- Paper/shadow runtime only.
- Candidate generation remains non-executable until downstream owners approve it.
- ORB evidence fields remain evidence rather than execution truth.
- VWAP reclaim-and-hold labels appear consistently.
- No rejected or fallback data becomes execution-eligible.
- No broker order is permitted as part of this proof.

This proof has not occurred in this PR.

Edge validation remains a separate pre-merge task against the unmerged PR 682
head.

## What This PR Does Not Prove

This PR does not prove profitability, structural edge, WFA success, live readiness, production certification, execution authority, capital allocation quality, Trend Pullback correctness, or Compression Breakout correctness.

## Human Approval

The human-approved scope was limited to the ORB mathematical correction and VWAP behavioral-identity correction.

V1 remains historical. V2 owns current repaired source identity. PR 682 remains draft. Merging requires separate explicit human approval after all CI checks pass.
