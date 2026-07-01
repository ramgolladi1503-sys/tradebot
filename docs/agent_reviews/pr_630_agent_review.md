# PR 630 Agent Review: Movement Strategy Profiles WFA Safe

## Agent Work Contract

### Scope

```text
Audit and refactor active movement strategies so they remain read-only StrategyCandidate generators, but become WFA-ready, parameter-profile-driven, and promotion-controlled.
```

- mode: PAPER
- candidate_id: N/A
- decision: ADVISORY_ONLY
- reason: Safe Refactor
- timestamp: 2026-07-01
- is_order_action: false
- broker_api_called: false
- source: GSD
- source_agent: Antigravity
- action: STRATEGY_PROFILES_REFACTOR
- title: Refactor movement strategies for WFA-safe parameter profiles
- scope: core, strategies, tests
- requested_paths: core/opportunity_scoring.py, core/strategy_parameter_profiles.py, strategies/movement/*, tests/*
- allowed_paths: core/opportunity_scoring.py, core/strategy_parameter_profiles.py, strategies/movement/*, tests/*
- forbidden_paths: core/broker*, core/execution*, core/order*
- expected_tests: tests/test_opportunity_scoring.py, tests/test_strategy_generators_lineage.py
- acceptance_proof: 39 passing tests and evidence that candidates get tagged with ADVISORY_ONLY
- read_only: true
- allowed_for_live_execution: false
- append: false

### Files Changed

- core/opportunity_scoring.py
- core/strategy_parameter_profiles.py
- docs/audits/strategy_contract_and_edge_readiness_audit.md
- strategies/movement/*
- tests/*

### Files Not To Touch

- broker adapters
- live execution paths
- dashboard runtime behavior
- unrelated strategy logic
- unrelated tests

### Expected Proof

- docs updated
- scanner/checker tests if implementation PR
- report evidence if audit run PR
- no live/broker/runtime execution

## Grill Me Review

### Challenge

```text
What assumption could be wrong? That the promotion state enforcement does not drop candidates incorrectly for strategies that are not configured properly, or that fallback scenarios are inadvertently allowed.
```

### Weaknesses Found

- Some tests initially didn't pass strict enforcement of `promotion_state` in opportunity scoring.

### Verdict

PASS

## Hermes Review

### Scope Check

- [x] No unrelated behavior changed.
- [x] No broker calls introduced.
- [x] No live behavior introduced.
- [x] No dashboard behavior introduced unless scoped.
- [x] No target runtime execution.
- [x] `UNKNOWN` is not treated as safe.

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Purpose is clear.
- [x] Scope is narrow.
- [x] Evidence exists.
- [x] Tests exist if code was added.
- [x] Report output exists if audit was run.
- [x] Next action is clear.

### Verdict

PASS

## QA / Safety Review

- Verified that `PROMOTED` is explicitly checked and everything else defaults to `ADVISORY_ONLY`.

### Verdict

PASS

## Scope Guard

### In Scope

- Moving heuristic constants to `DEFAULT_PROFILES`.
- Injecting `params_hash` and `promotion_state` into the lineage.
- Enforcing `promotion_state` in opportunity scoring.

### Out of Scope

- Modifying order behavior or broker logic.
- Live trading activation.

### Boundary Verification

- [x] No broker calls.
- [x] No live runtime execution.
- [x] No target repo mutation by scanner.
- [x] No auto-fix.
- [x] No auto-PR.
- [x] No external agent automation.

## High-Risk Path Review

### Execution Risk

- The changes modify `core/opportunity_scoring.py` and `strategies/movement/*`.
- Opportunity scoring strictly defaults to penalizing the candidate to `ADVISORY_ONLY` if it doesn't explicitly have the `PROMOTED` state. This prevents unverified strategies from executing live.
- The default profile lookup defaults to `ADVISORY_ONLY` if the strategy version is not actively tracked as `PROMOTED`.

### Verification

- Generator-level tests verify that `promotion_state` is attached to `StrategyCandidate` outputs.
- Test suites have been run and verified to ensure no inadvertent executability of fallback or stale logic.

## Acceptance Proof

The PR was manually reviewed against the project requirements.
- Tests prove that `ADVISORY_ONLY` prevents executable scores.
- Documentation in `docs/audits/strategy_contract_and_edge_readiness_audit.md` explicitly lists constant equality proofs.

## Runtime Proof Required After Merge

None explicitly, aside from standard staging execution validation of movement strategies in paper mode to ensure they generate correct `ADVISORY_ONLY` signals without crashing.

## What This PR Does Not Prove

This PR does not prove profitability or edge for any of the active movement strategies. It merely provides the required tracking mechanism for future WFA edge discovery.

## Human Approval

Approved by user via conversation prompts.

## Evidence

### Commands Run

```bash
pytest -q tests/test_candidate_pool.py tests/test_opportunity_scoring.py tests/test_opportunity_scoring_regime_profile_opt_in.py tests/test_strategy_generators_lineage.py
```

### Reports / Files Produced

- docs/audits/strategy_contract_and_edge_readiness_audit.md
- core/opportunity_scoring.py
- core/strategy_parameter_profiles.py
- tests/test_strategy_generators_lineage.py

### Final Verdict

PASS
