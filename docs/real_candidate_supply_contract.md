# Real Candidate Supply Contract

This contract is offline-only and deterministic. It demonstrates that TradeBuilder can supply one real ranked candidate from strong clean LIVE-like inputs without broker calls, runtime wiring, Kite/websocket dependency, or Phase2/ranking changes.

The contract is read-only and fails closed.

## Scope

- Prove that a clean live-like market snapshot can produce a real ranked candidate in the TradeBuilder pool.
- Prove that a missing-signal path with fallbacks disabled does not create a ranked candidate.
- Prove that missing bid/ask prevents a real candidate from reaching the pool.
- Prove that no broker or runtime side effects occur.

## Safety Constraints

- Closed/off-market test and review scope only.
- No live orders.
- No broker/order changes.
- No Kite/websocket dependency.
- No runtime behavior changes.
- No strategy/ranking/Phase2/dashboard changes.
- No FeedTruth/audit changes.
- No broad refactor.
- No weakening of safety gates.

## Contract Expectations

- Input fixtures are synthetic and deterministic.
- The live-like case must produce a real ranked candidate from strong clean inputs.
- The no-signal case must remain empty when fallbacks are disabled.
- The missing-bid/ask case must not enter the real candidate pool.
- The builder must not call broker or runtime actions.

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_trade_builder_real_candidate_supply.py -vv`
- `PYTHONPATH=. pytest -q tests/test_trade_builder_real_candidate_supply.py tests/test_trade_builder.py tests/test_trade_builder_candidate_breadth.py tests/test_trade_builder_soft_vetoes.py tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv`

## Validation Commands

- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `git diff --name-status origin/main...HEAD`
- `git diff --name-only origin/main...HEAD | grep -E "kite_depth_ws|strategies/|strategy|phase2|broker|execution_engine|dashboard|streamlit|runtime_execution_truth|feed_truth_contract|feed_truth_audit" && echo "FORBIDDEN SCOPE TOUCHED" && exit 1 || true`
- `git diff --name-only origin/main...HEAD | grep -E "place_order|modify_order|cancel_order|exit_order|broker_api|broker.*call|live_mode|ENABLE_LIVE|quote_freshness_contract_failed" && echo "SAFETY SCOPE TOUCHED" && exit 1 || true`

## Expected Changed Files

- `tests/test_trade_builder_real_candidate_supply.py`
- `docs/real_candidate_supply_contract.md`
- `docs/agent_reviews/real-candidate-supply-contract.md`

## Forbidden Scope Not Touched

- `strategies/trade_builder.py`
- `core/broker*`
- `core/order*`
- `core/kite_depth_ws.py`
- `core/orchestrator.py`
- `core/runtime_execution_truth.py`
- `core/feed_truth_contract.py`
- `dashboard/*`
- `runtime/*`
- `logs/*`

## Risk Assessment

- Low risk because this is offline-only and test-driven.
- The main risk is over-asserting execution readiness in the helper inputs; that is addressed by asserting only real candidate pool membership and non-synthetic provenance, not live broker action.

## Rollback Plan

- Remove the test file and docs if the contract becomes invalid.
- Keep production code unchanged unless a real production bug is proven separately.

## Why This Does Not Prove Trading Edge

- It only proves deterministic candidate supply under controlled inputs.
- It does not prove profitability, robustness, or live-market edge.
- It does not exercise runtime execution, broker routing, or live order placement.

## Future Work Out of Scope

- Runtime wiring of this contract.
- Live/session integration.
- Any change to ranking, Phase2, broker/order, or risk gates.
- Any decision to use this contract for live trading.
