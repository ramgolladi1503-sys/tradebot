# PR #521 — Candidate Supply Zero Attribution

mode: REVIEW
candidate_id: PR-521-CANDIDATE-SUPPLY-ZERO-ATTRIBUTION
decision: fix_candidate_supply_zero_attribution
reason: Make raw_candidate_count=0 explainable with timeline-driven candidate-supply subtypes while preserving current-session RCA precedence and stale-tail diagnostics.
timestamp: 2026-06-08T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/candidate-supply-zero-attribution.md

## Agent Work Contract
- **source_agent:** GSD
- **action:** Generate scoped patch, tests, docs, and validation for candidate supply zero attribution
- **title:** Candidate Supply Zero Attribution
- **scope:** Explain raw_candidate_count=0 with subtype attribution, timeline ordering, and current-session vs historical-tail evidence scopes without changing runtime trading behavior
- **requested_paths:** `core/agents/candidate_supply_agent.py`, `core/agents/live_rca_agent.py`, `core/agents/command_center.py`, `core/agents/readers.py`, `scripts/run_tradebot_agent_command_center.py`, `tests/test_candidate_supply_agent.py`, `tests/test_agent_command_center.py`, `tests/test_live_rca_agent.py`, `docs/agent_reviews/candidate-supply-zero-attribution.md`
- **allowed_paths:** Same as requested paths
- **forbidden_paths:** `core/kite_depth_ws.py`, `core/orchestrator.py`, `core/candidate_scoring.py`, `core/expectancy/*`, `core/review_queue.py`, `strategies/*`, `dashboard/*`, broker/order/execution files, websocket runtime files, Phase2/ranking math files
- **expected_tests:** `PYTHONPATH=. pytest -q tests/test_candidate_supply_agent.py tests/test_agent_command_center.py tests/test_live_rca_agent.py -vv`
- **acceptance_proof:** Candidate supply zero becomes subtype-specific; historical feed churn remains diagnostic-only when current-session feed is fresh; command center recommendation points to the first current-session supply blocker

## Scope Guard
- Do not change strategy generation, scoring, ranking, Phase2, feed lifecycle, websocket behavior, broker adapters, orders, or dashboard behavior.
- Do not weaken stale-feed safety.
- Do not hide failures; label them accurately.
- Do not let historical feed churn overwrite the first current-session candidate-supply blocker.

## Grill Me Review
- If `raw_candidate_count=0` is still one vague bucket, the RCA is not actionable enough.
- If historical feed churn can still dominate when current-session feed health is good, the attribution is wrong.
- If latency guard or SLO evidence is lost instead of ordered, the RCA is incomplete.

## Hermes Review
- Keep `readers.py` parsing-only.
- Let `candidate_supply_agent.py` own the candidate-supply subtype classification.
- Preserve evidence scopes so the command center can distinguish `current_session`, `historical_tail`, and `mixed`.
- Keep subtype ordering timeline-driven; use stable priority only when timestamps are equal or missing.

## GSD Review
- Add deterministic subtype extraction for strategy qualification, regime instability, latency guard cooldown, latency guard degrade-exit-only, SLO/feed stale, trade-builder reached/no candidate, and trade-builder not reached.
- Add candidate-supply evidence scope and feed-churn evidence scope metrics.
- Update command center recommendation text to be subtype-specific.
- Add tests proving the first subtype and the diagnostic ordering.

## QA / Safety Review
- Verify reports remain read_only and non-ordering.
- Verify stale historical churn remains visible but diagnostic-only when current-session feed freshness is healthy.
- Verify current-session strategy qualification / candidate-supply evidence can drive the blocker instead of stale feed churn.
- Verify no strategy, ranking, Phase2, broker, order, dashboard, or websocket runtime behavior changed.

## Live Evidence Summary
- Fresh current-session feed health can coexist with historical tail feed churn.
- The current-session blocker for `raw_candidate_count=0` is now attributed to candidate supply subtype evidence rather than a generic bucket.
- The first subtype is driven by the earliest current-session candidate-supply-zero event; later latency/SLO evidence remains visible as secondary diagnostics.

## What Changed
- Added candidate-supply subtype attribution and timeline ordering.
- Added `candidate_supply_evidence_scope` and `feed_churn_evidence_scope`.
- Added command-center subtype-specific recommendation text.
- Preserved current-session precedence and stale-tail diagnostics.

## What Was Not Changed
- Strategy generation.
- Strategy thresholds.
- Ranking / scoring / Phase2 logic.
- Feed lifecycle runtime behavior.
- Broker / order / execution behavior.
- Dashboard / UI behavior.

## Safety Summary
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- No runtime mutation outside evidence classification and RCA text.

## Tests Run
- `PYTHONPATH=. pytest -q tests/test_candidate_supply_agent.py tests/test_agent_command_center.py -vv`
- `PYTHONPATH=. pytest -q tests/test_live_rca_agent.py -vv`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py`

## Acceptance Proof
- Candidate supply zero is no longer one vague bucket.
- Historical feed churn remains visible as diagnostics but does not dominate the command center when current-session feed is fresh.
- Strategy qualification, regime instability, latency guard, and SLO/feed stale causes are separated.
- Later latency/SLO blockers do not overwrite the first candidate-supply cause.
- No strategy, ranking, scoring, feed lifecycle, broker, order, dashboard, or Phase2 behavior changed.

## Runtime Proof Required After Merge
- Run `PYTHONPATH=. python scripts/run_tradebot_agent_command_center.py --runtime-dir .runtime --logs-dir logs --out-dir .runtime/agent_reports --agents all --format both` on current evidence.
- Re-run `python scripts/validate_agent_review_evidence.py --base-ref origin/main`.
- Re-run the repo CE gate on the changed paths file.

## What This PR Does Not Prove
- It does not prove the strategy layer generates enough candidates.
- It does not prove market edge.
- It does not prove feed churn can never happen.
- It does not change runtime trading behavior.

## Human Approval
- Approved for scoped implementation only if candidate supply zero is explained by subtype evidence and stale historical churn does not dominate the current-session blocker.
- If current-session feed health is fresh, the next PR recommendation must not be a false feed lifecycle stabilization call.

## Rollback Plan
- Revert `core/agents/candidate_supply_agent.py` and `core/agents/command_center.py` together if attribution proves misleading in live evidence.
- Keep the doc and tests as the rollback verification baseline only if the code revert is required.
- Re-run the focused tests and command-center evidence generation after any rollback.


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
