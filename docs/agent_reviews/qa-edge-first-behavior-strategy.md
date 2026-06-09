# QA Gate Foundation + Fallback Executable Firewall — Agent Review Evidence

mode: PAPER
candidate_id: qa-edge-first-behavior-strategy-pr542
decision: fallback-executable-firewall-added
reason: Prevent fallback-derived quote evidence from being promoted into executable top opportunities and lock edge-first QA governance.
timestamp: 2026-06-09T11:27:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/qa-edge-first-behavior-strategy.md

## Agent Work Contract

This PR establishes the edge-first QA governance foundation for Tradebot and fixes one proven top-opportunity selector safety gap.

The work is intentionally scoped to:

- QA documentation and scope definition.
- pytest marker taxonomy for behavior, safety, edge, regression, replay, chaos, UI read-model, and broker-firewall tests.
- fallback executable firewall behavior tests.
- selector fallback-truth normalization so fallback-derived rows cannot become executable when upstream fields claim EXECUTE.

All tests added in this PR must protect, prove, measure, or improve trading edge.

## Scope Guard

In scope:

- `docs/qa/*` QA governance documents.
- `pytest.ini` marker taxonomy.
- `tests/behavior/test_top_opportunity_edge_behavior.py`.
- `core/expectancy/top_opportunity_selector.py` fallback truth normalization.

Out of scope:

- feed/WebSocket behavior changes.
- broker adapter changes.
- execution engine changes.
- strategy generation changes.
- dashboard behavior changes.
- live-market validation.
- experimental local feed branch changes.

## Grill Me Review

Question: Does this PR merely add documentation without proving behavior?

Answer: No. It adds a failing-first behavior regression that proved fallback quote data could become executable when the row claimed `fallback_used=False`, then fixes selector normalization.

Question: Could this hide real executable candidates?

Answer: The positive clean-live test proves a real live, expectancy-positive candidate remains executable after the fallback firewall.

Question: Does this test current behavior or intended behavior?

Answer: Intended behavior. The first test intentionally failed before the fix because fallback-derived quote data must never be executable.

## Hermes Review

Coordination notes:

- This PR is a foundation PR for future QA work.
- It should be merged before broader coverage-map PRs.
- Future PRs should follow the QA Gate docs added here.
- The branch must not include unrelated local experimental feed changes.

## GSD Review

Governance / Scope / Discipline result:

- Single theme: edge-first QA foundation plus one proven selector safety fix.
- No unrelated refactor.
- No broad architecture rewrite.
- No hidden live behavior.
- No weakening of existing tests.
- No fake happy-path-only coverage.

## QA / Safety Review

Safety findings:

- No broker calls added.
- No order calls added.
- No WebSocket calls added.
- No live network dependency added.
- Selector remains read-only.
- Fallback-derived rows are forced into non-executable classification.
- Clean live executable path remains covered.

Edge protection:

- Prevents fake top opportunities from fallback, recovered, synthetic, soft-rejected, or subscription-failed quote sources.
- Preserves trading-edge selection for clean live candidates.

## Acceptance Proof

Local focused tests passed:

```bash
pytest tests/behavior/test_top_opportunity_edge_behavior.py -q
# 9 passed

pytest tests/test_top_opportunity_selector.py tests/behavior/test_top_opportunity_edge_behavior.py -q
# 20 passed
```

Behavior proven:

- `REST_FALLBACK` cannot become executable.
- `SYNTHETIC_OFFHOURS` cannot become executable.
- `SUBSCRIPTION_FAILED` cannot become executable.
- `row_kind=recovered_fallback` cannot become executable.
- `candidate_class=fallback` cannot become executable.
- `candidate_type` containing fallback cannot become executable.
- `candidate_origin` containing fallback cannot become executable.
- `softrej_` trade IDs cannot become executable.
- Clean live candidate can still become executable.

## Runtime Proof Required After Merge

Runtime/live-market proof is not required for this PR because it does not change feed runtime, broker runtime, WebSocket lifecycle, strategy generation, dashboard runtime wiring, or execution engine behavior.

Recommended post-merge verification:

```bash
pytest tests/behavior/test_top_opportunity_edge_behavior.py -q
pytest tests/test_top_opportunity_selector.py tests/behavior/test_top_opportunity_edge_behavior.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

## What This PR Does Not Prove

This PR does not prove:

- full Tradebot test coverage.
- feed stability.
- live WebSocket freshness.
- broker integration correctness.
- strategy profitability.
- dashboard read-model completeness.
- replay/backtest profitability truth.
- end-to-end candidate generation quality.

Those are intentionally left for future QA roadmap PRs.

## Human Approval

Human approval required before merge.

Recommended approval condition:

- Agent Review Evidence Gate passes.
- Focused selector tests pass.
- PR diff confirms no unrelated experimental feed files are included.
- Maintainer confirms the fallback firewall behavior matches intended trading product safety.
