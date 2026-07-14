# PR 636 Agent Review

## Agent Work Contract
- Source agent: Codex
- Action: cleanup and CI fix
- Title: Tighten ranking proof-pack feed risk truth and remove import-time YAML dependency from CI-sensitive tests
- Scope: proof-pack ranking truth, CI import hygiene, and PR scope cleanup
- Requested paths: core/candidate_ranking.py, scripts/run_candidate_ranking_proof_pack.py, scripts/run_option_data_quality_proof_pack.py, tests/test_candidate_ranking.py, tests/test_candidate_ranking_proof_pack.py, tests/test_option_data_quality_proof_pack.py
- Allowed paths: the files above plus docs/agent_reviews/pr636_ranking_proof_pack_truth.md
- Forbidden paths: broker code, order code, risk gate weakening, feed gate weakening, unrelated opening-drive scratch artifacts
- Expected tests: targeted ranking/proof-pack pytest slice
- Acceptance proof: unsafe IV-surface scenarios are non-executable in ranking and the clean scenario remains executable; CI import-time YAML failures are removed on the clean branch

## Scope Guard
- This PR is read-only evidence and ranking truth hardening.
- It does not place orders, call broker APIs, or weaken execution or freshness gates.
- It does not touch unrelated opening-drive scratch work or runtime artifacts.

## Grill Me Review
- Ranking previously leaked executable truth for an unsafe IV-surface scenario.
- The proof-pack runner assumed a rank field that was not stable across the branch history.
- The clean branch was rebuilt to remove unrelated diff noise before CI recheck.

## Hermes Review
- The canonical flow is raw candidate -> pool -> normalization -> classification -> hard downgrade -> scoring -> ranking -> execution firewall.
- IV-surface weakness must be visible before final execution gating, not only after it.
- The proof pack now asserts that unsafe quote-state scenarios are non-executable in ranking.

## GSD Review
- Files changed are limited to the proof-pack/ranking truth slice and this review file.
- The branch was cleaned by cherry-picking only the relevant commits onto a worktree from `origin/main`.
- A defensive `candidate_id` fallback was added so the proof pack matches the branch rank schema.

## QA / Safety Review
- `PYTHONPATH=. pytest -q tests/test_candidate_ranking.py tests/test_option_data_quality_proof_pack.py tests/test_candidate_ranking_proof_pack.py tests/test_ranking_orchestrator.py tests/test_opportunity_engine_truth_guard.py`
- Result on the clean branch: `42 passed`
- High-risk path review: only ranking-proof and read-only CI compatibility paths were touched; no broker, order, live, or risk-gate code was modified.

## Acceptance Proof
- `iv_surface_slope_preserved` and `iv_term_missing_preserved` remain non-executable in ranking.
- `clean_live_quote` remains executable in ranking.
- The proof-pack runner now tolerates rank records without a dedicated `candidate_id` field.

## Runtime Proof Required After Merge
- Re-run the full PR checks on GitHub Actions after pushing the cleaned branch.
- Confirm `agent-review-evidence`, `code-excellence-gates`, and `unit_tests` go green.

## What This PR Does Not Prove
- It does not prove profitability.
- It does not prove live broker execution.
- It does not prove unrelated opening-drive work is valid.

## Human Approval
- Required before any live execution, broker changes, or risk-threshold changes.

## Evidence Audit Fields
mode: LIVE
candidate_id: PR636-RANKING-PROOF
decision: BLOCK fallback legacy execution
reason: Fallback data not executable
timestamp: checked
is_order_action: false
broker_api_called: false
source: agent

## Traceability Checklist
mode: LIVE
candidate_id: PR636-RANKING-PROOF
decision: BLOCK fallback legacy execution
reason: Fallback data not executable
timestamp: checked
is_order_action: false
broker_api_called: false
source: agent_review


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
