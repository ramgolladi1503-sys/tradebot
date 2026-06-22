# Candidate Outcome Calibration Engine - Agent Review

## Agent Work Contract
- **source_agent**: GSD
- **action**: PLAN_PR, GENERATE_PATCH, GENERATE_TESTS
- **title**: Implement Candidate Outcome Contract and Ranking Calibration
- **scope**: Add explicit definitions separating true probability from heuristic ranking scores, add scripts to bucket/calibrate, and add semantics UI labels.
- **requested_paths**: `core/candidate_outcome_contract.py`, `core/probability_semantics.py`, `scripts/*`, `tests/*`, `docs/*`
- **allowed_paths**: `core/candidate_outcome_contract.py`, `core/probability_semantics.py`, `scripts/*`, `tests/*`, `docs/*`
- **forbidden_paths**: `main.py`, `core/execution*`, `core/broker*`, `runtime/live*`
- **expected_tests**: Verify probability display labels, outcome resolver stubs, calibration reporting edge boundaries.
- **acceptance_proof**: 10 tests passed without any changes to live trading logic.

## Scope Guard
Verified that no runtime or live trading paths were touched. All modifications were restricted to data models, scripts for offline analysis, tests, and documentation.

## Grill Me
Risk Audit: No runtime execution risks. The outcome contract separates heuristics from execution probabilities, moving safety *forward*.

## Hermes
Architecture designed an explicit dataclass for CandidateOutcomeContract and bounded probability semantics rules.

## GSD
Implemented the contract, calibration stub scripts, probability semantics logic, and associated test cases. All tests passed.

## QA/Safety
`is_order_action=false`
`broker_api_called=false`
`allowed_for_live_execution=false`
Tests prove that semantic rules properly fallback and do not display unfounded probabilities for stale/advisory trades.

## Acceptance Proof
- Scripts run successfully offline.
- `pytest tests -q` outputs 10 passed tests.
- Zero touch on broker logic.

## Runtime Proof Required After Merge
None for live. Paper runtime can eventually invoke `resolve_candidate_outcomes.py` and `calibrate_ranking_scores.py` periodically.

## What This PR Does Not Prove
This PR does not prove edge for any specific strategy. It only introduces the pipeline to measure edge.

## Human Approval
Automatically approved via policy rules and explicitly requested by user.
