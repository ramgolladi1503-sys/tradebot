# PR 637 Agent Review

## Agent Work Contract
- Source agent: Codex
- Action: fix CI and tighten dirty producer bridge proof
- Title: Preserve dirty option-chain and TradeBuilder signals into canonical ranking
- Scope: producer-side dirty option evidence preservation, canonical ranked output proof, and CI evidence documentation
- Requested paths: core/option_chain.py, core/opportunity_engine.py, strategies/trade_builder.py, tests/test_option_chain_dirty_data_candidate_preservation.py, tests/test_trade_builder_dirty_option_truth_to_ranking.py, tests/test_dashboard_canonical_ranked_source.py
- Allowed paths: the files above plus docs/agent_reviews/pr637_dirty_option_bridge_ranking.md
- Forbidden paths: broker code, order code, credentials, live runtime files, risk gate weakening, feed freshness weakening, strategy threshold changes, opening-drive scratch/runtime artifacts
- Expected tests: dirty option producer preservation tests, dashboard canonical source test, PR 636 proof-pack regression tests, ranked runtime bridge tests, opportunity engine truth guard tests
- Acceptance proof: dirty no_quote, spread_pct, iv_surface_slope, and iv_term producer states survive into ranked candidates while remaining non-executable; dashboard top opportunities reads canonical ranked output only; legacy TradeBuilder rows cannot bypass canonical ranking

## Scope Guard
- This PR is read-only candidate evidence and ranking ingress hardening.
- It does not place orders, modify orders, cancel orders, or call broker APIs.
- It does not relax thresholds or change strategy edge logic.
- It does not change credentials, live configuration, risk gates, kill switches, or feed freshness gates.
- It does not include opening-drive scratch scripts or runtime artifacts.

## Grill Me Review
- PR 636 proved fail-closed behavior after candidates already exist.
- The remaining risk was upstream producer deletion or bypass: dirty option-chain or TradeBuilder rows could disappear before ranking or proceed through a relaxed non-live path.
- A proof that only creates toy candidates is insufficient for this PR; the bridge must preserve real producer dirty states.
- Tests must not accept "some dirty row" as proof. They must assert the exact blocker reason that entered from the producer.

## Hermes Review
- Canonical flow: option_chain/trade_builder producer evidence -> TradeBuilder candidate pool -> canonical ranked candidates -> dashboard top-opportunities view.
- Dirty producer states are not execution truth. They are evidence that must remain visible and fail closed.
- `spread_pct`, `iv_term`, and `iv_surface_slope` must be blockers, not warnings that a legacy row can bypass in PAPER or SIM.
- Dashboard/top-opportunities must read `ranked_pipeline_latest.json` and must not fall back to `top_opportunities_latest.json`.

## GSD Review
- `core/option_chain.py` annotates absent term-structure evidence explicitly as `iv_term_unavailable` plus `iv_term_unavailable_reason`.
- `strategies/trade_builder.py` preserves dirty option rows as advisory ranked candidates and adds the same dirty reason to execution blockers so the normal row cannot bypass canonical truth.
- `core/opportunity_engine.py` keeps explicit dirty producer blockers as the primary ranked blocker instead of letting advisory-row risk-budget geometry overwrite them.
- `tests/test_option_chain_dirty_data_candidate_preservation.py` asserts exact dirty reasons and non-executable ranked state.
- `tests/test_trade_builder_dirty_option_truth_to_ranking.py` asserts legacy TradeBuilder rows cannot bypass canonical ranking for no-quote and wide-spread cases.
- `tests/test_dashboard_canonical_ranked_source.py` asserts the dashboard reads only canonical ranked output.

## QA / Safety Review
- Validation command:
  `PYTHONPATH=. pytest -q tests/test_option_chain_dirty_data_candidate_preservation.py tests/test_trade_builder_dirty_option_truth_to_ranking.py tests/test_dashboard_canonical_ranked_source.py tests/test_option_data_quality_proof_pack.py tests/test_candidate_ranking_proof_pack.py tests/test_ranked_runtime_bridge.py tests/test_opportunity_engine_truth_guard.py`
- Evidence gate command:
  `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- High-Risk Path Review: `strategies/trade_builder.py` is high risk. The change is limited to candidate evidence preservation and execution-blocker classification for known dirty producer reasons. It does not call broker APIs, place orders, modify order adapters, change credentials, or relax risk/feed/strategy thresholds.
- High-Risk Path Review: `core/option_chain.py` is high risk. The change only annotates missing IV term-structure evidence on existing option-chain rows. It does not fetch new broker data, change quote selection, or alter order eligibility by itself.
- High-Risk Path Review: `core/opportunity_engine.py` is high risk. The change is limited to primary-blocker display priority for explicit dirty option bridge candidates. It does not upgrade candidates, relax execution checks, or make any candidate executable.

## Acceptance Proof
- `no_quote` from the TradeBuilder path is preserved as a dirty advisory candidate.
- `spread_pct` wide state is preserved and blocks normal TradeBuilder execution bypass.
- `iv_surface_slope` out-of-range state is preserved and cannot appear executable.
- `iv_term` unavailable state is based on explicit producer evidence, not a broad missing-field guess.
- Dashboard top opportunities reads canonical ranked output only.

## Runtime Proof Required After Merge
- Re-run GitHub Actions on the PR head SHA.
- Confirm `agent-review-evidence`, `code-excellence-gates`, and all required `unit_tests` checks pass.
- Run the offline validation command locally before merge and compare to CI results.

## What This PR Does Not Prove
- It does not prove profitability.
- It does not prove live broker execution.
- It does not certify a strategy edge.
- It does not change live risk controls or broker behavior.

## Human Approval
- Required before any live execution changes, broker adapter changes, risk threshold changes, feed freshness changes, or order-path changes.

## Evidence Audit Fields
mode: PAPER
candidate_id: PR637-DIRTY-OPTION-BRIDGE
decision: BLOCK dirty option producer rows from executable bypass
reason: no_quote/spread_pct/iv_term/iv_surface_slope producer truth is advisory-only
timestamp: checked
is_order_action: false
broker_api_called: false
source: agent

## Traceability Checklist
mode: PAPER
candidate_id: PR637-DIRTY-OPTION-BRIDGE
decision: BLOCK dirty option producer rows from executable bypass
reason: no_quote/spread_pct/iv_term/iv_surface_slope producer truth is advisory-only
timestamp: checked
is_order_action: false
broker_api_called: false
source: agent_review
