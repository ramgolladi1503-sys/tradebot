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
- acceptance_proof: `ORB_OUTCOMES_MEASURED`

## Scope Guard

This PR is research-only underlying outcome measurement work. It measures the full certified ORB candidate corpus against read-only underlying OHLCV sources, does not calculate option P&L, does not modify production files, and does not call brokers.

## Repository Evidence Fields

- mode: RESEARCH_UNDERLYING_OUTCOME_MEASUREMENT
- candidate_id: opening_range_retest_outcome_methodology
- decision: ORB_OUTCOMES_MEASURED
- reason: Full certified ORB candidate accounting is implemented with strict read-only source binding, legal-entry enforcement, forward returns, MFE/MAE, path-event classification, duplicate exposure reporting, and deterministic artifact audit.
- timestamp: 2026-07-19T04:20:00+05:30
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

The framework includes contract objects, forward returns, excursions, stop/target path events, exposure detection, an ORB adapter, artifact writing, full-corpus generation, and strict independent audit. Candidates without a strictly later bar are retained as `NO_LEGAL_ENTRY`, not dropped or silently treated as measured.

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Focused tests cover unsupported direction rejection, deterministic candidate hashing, no same-bar entry, directional forward return, MFE/MAE, same-bar path ambiguity, duplicate exposure, duplicate timestamp rejection, artifact writing, certified-ledger adapter mapping, OHLCV timestamp canonicalization, and canonical outcome hashing.

## Runtime Proof Required After Merge

The full certified candidate ledger must be run twice from the same frozen clean commit in independent output directories. The audits must reconcile:

- certified candidate count: `2215`
- certified candidate semantic hash: `53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24`
- certified source count: `1512`
- certified source-universe hash: `cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc`
- all candidates accounted by explicit status
- deterministic A/B outcome semantic hash equality

The full-run summary records `MEASURED` candidates separately from candidates with no strictly later legal entry bar.

## What This PR Does Not Prove

This PR does not certify `ORB_OUTCOMES_MEASURED`, structural edge, profitability, exact option P&L, option fills, spread realization, slippage, latency, paper readiness, live readiness, execution readiness, capital allocation readiness, broker correctness, or production promotion.

## Human Approval

Human review and merge are required. Codex must not merge this PR or enable auto-merge.
