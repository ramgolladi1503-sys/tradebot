# Opening Range Retest Outcome Methodology

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Define ORB underlying outcome methodology
- scope: Research-only descriptive underlying outcome measurement for the certified ORB candidate ledger.
- requested_paths: `research/strategy_outcomes/**`, `scripts/generate_opening_range_retest_outcomes.py`, `scripts/audit_opening_range_retest_outcomes.py`, `tests/test_strategy_outcomes_*.py`, `tests/test_opening_range_retest_outcomes_adapter.py`, `docs/agent_reviews/opening_range_retest_outcome_methodology.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: focused strategy outcome tests, py_compile, diff check, agent-review evidence validation, scoped CE gate
- acceptance_proof: `ORB_OUTCOME_FRAMEWORK_IMPLEMENTED_NO_FULL_RUN`

## Scope Guard

This PR is research-only framework work. It does not run the full ORB outcome corpus, does not calculate option P&L, does not modify production files, and does not call brokers.

## Repository Evidence Fields

- mode: RESEARCH_OUTCOME_FRAMEWORK
- candidate_id: opening_range_retest_outcome_methodology
- decision: ORB_OUTCOME_FRAMEWORK_IMPLEMENTED_NO_FULL_RUN
- reason: Free disk is below the required 6 GiB threshold, so only the lightweight framework and focused tests are in scope.
- timestamp: 2026-07-19T03:20:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/opening_range_retest_outcome_methodology.md

## Grill Me Review

This methodology is descriptive outcome measurement only. It is not WFA, not an edge verdict, and not a promotion signal.

## Hermes Review

Contract decisions:

- Entry timing: first legal bar strictly after `proposal_ready_at`.
- Horizons: 1, 3, 5, 10, 15, 30 minutes.
- MFE/MAE: measured from the legal entry reference price through each horizon using underlying OHLC bars.
- Stop/target ambiguity: same-bar stop and target crossing is recorded as `AMBIGUOUS_SAME_BAR`.
- Overlap policy: duplicate directional exposure is reported, not silently collapsed.
- Claim boundary: underlying descriptive movement only.

## GSD Review

The framework includes contract objects, forward returns, excursions, stop/target path events, exposure detection, an ORB adapter, artifact writing, and audit scaffolding. The full run remains closed until disk is above the required threshold.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Focused tests cover unsupported direction rejection, deterministic candidate hashing, no same-bar entry, directional forward return, MFE/MAE, same-bar path ambiguity, duplicate exposure, duplicate timestamp rejection, artifact writing, and ORB adapter mapping.

## Runtime Proof Required After Merge

Before `ORB_OUTCOMES_MEASURED`, run the full certified candidate ledger twice in independent output directories, reconcile candidate/source counts and hashes, require equal semantic hashes, and pass independent audit.

## What This PR Does Not Prove

This PR does not certify `ORB_OUTCOMES_MEASURED`, structural edge, profitability, exact option P&L, option fills, spread realization, slippage, latency, paper readiness, live readiness, execution readiness, capital allocation readiness, broker correctness, or production promotion.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
