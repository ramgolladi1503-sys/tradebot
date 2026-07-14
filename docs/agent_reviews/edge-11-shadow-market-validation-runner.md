mode: REVIEW
candidate_id: EDGE-11-SHADOW-MARKET-VALIDATION-RUNNER
decision: add_shadow_market_validation_runner
reason: Add a read-only shadow validation runner that evaluates live/paper candidates without placing trades and writes append-only evidence artifacts.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-11-shadow-market-validation-runner.md

# Agent Work Contract

## Scope Guard
- This PR only adds a read-only shadow validation runner and report writer.
- No broker, order, strategy, ranking, dashboard, websocket, or feed lifecycle behavior changes are allowed.
- The runner must only validate and summarize evidence; it must not place or simulate live orders.

## Grill Me Review
- The runner must fail closed when required inputs are absent.
- Fallback and blocked candidates must remain separate from executable validation statistics.
- The report must not imply that shadow evidence authorizes live trading.

## Hermes Review
- The runner is a read-only evidence aggregator over existing candidate journal, outcome, and top-opportunity artifacts.
- Session evidence is append-only under `.runtime/shadow_validation/`.
- The report should honestly distinguish executable, advisory, blocked, and fallback evidence.

## GSD Review
- Files touched are limited to the shadow validation module, CLI, tests, and this review doc.
- The implementation does not wire into live execution or broker integrations.
- Deterministic fixture coverage proves the runner output contract and failure behavior.

## QA / Safety Review
- `read_only: true`
- `append: true`
- `is_order_action: false`
- `broker_api_called: false`
- `live_order_allowed: false`
- `live_order_action: false`
- `broker_order_action: false`
- No Kite, Upstox, or broker calls are allowed.

## Acceptance Proof
- The runner writes session evidence to `.runtime/shadow_validation/session_<YYYYMMDD>.jsonl`.
- The runner writes latest JSON and Markdown reports under `.runtime/shadow_validation/`.
- Top-1 and top-3 results are derived from edge-ranked executable candidates.
- Fallback rows are excluded from executable validation statistics.
- Blocked candidates are counted separately.
- Missing inputs produce a safe diagnostic report instead of crashing.

## Runtime Proof Required After Merge
- Confirm the CLI exits zero for a valid fixture.
- Confirm the session JSONL file receives an appended evidence row.
- Confirm the Markdown report includes the summary, top-result, fallback, and feed-block sections.

## What This PR Does Not Prove
- It does not prove market edge or trading profitability.
- It does not enable live orders or broker execution.
- It does not replace the existing top-opportunity or expectancy reports.

## Human Approval
- This PR is read-only by design.
- Any future attempt to use shadow validation as execution input requires a separate approved PR.


## Agent Work Contract

N/A

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
