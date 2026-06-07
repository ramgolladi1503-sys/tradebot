mode: REVIEW
candidate_id: EDGE-06-SETUP-FINGERPRINT-CONTRACT
decision: add_setup_fingerprint_contract
reason: Add a deterministic setup fingerprint contract for candidates and outcomes so expectancy and journal rows can be grouped more precisely without changing runtime behavior.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-06-setup-fingerprint-contract.md

# Agent Work Contract

## Scope Guard
- This PR only adds deterministic setup fingerprint labels and wiring.
- No broker, order, strategy, ranking, UI, websocket, or feed lifecycle changes are allowed.
- No runtime kill/keep gate is introduced.

## Grill Me Review
- The fingerprint must be deterministic for the same logical row.
- Missing bucket inputs must fail closed into `UNKNOWN`, not crash.
- The fingerprint is metadata, not a trading decision.

## Hermes Review
- The contract adds stable setup labels that can be used for grouping and reporting.
- The setup identity is readable and reproducible across runs.
- Existing strategy/regime expectancy outputs remain unchanged unless explicit setup grouping is requested.

## GSD Review
- Files touched are limited to the setup fingerprint helper, narrow journal/outcome wiring, expectancy grouping, tests, and this review doc.
- No execution behavior changes are introduced.

## QA / Safety Review
- Read-only proof only.
- `is_order_action: false`
- `broker_api_called: false`
- `read_only: true`
- `append: false` for reports and `append: true` only for the existing journal/outcome append contracts.
- No live orders, no broker calls, no runtime mutation beyond metadata enrichment.

## Acceptance Proof
- Same input produces the same `setup_id`.
- Different regime or spread bucket changes the `setup_id`.
- Missing fields produce `UNKNOWN` buckets without crashing.
- Candidate journal rows and outcome rows include setup fingerprint fields when wired.
- Expectancy can optionally group by `setup_id` without changing the default strategy/regime report.

## Runtime Proof Required After Merge
- Confirm candidate journal rows include `setup_id` and bucket fields.
- Confirm candidate outcome rows include `setup_id` and bucket fields.
- Confirm default expectancy reports remain stable unless `group_by_setup_id=True` is requested.

## What This PR Does Not Prove
- It does not prove trading edge.
- It does not prove a better strategy.
- It does not change ranking or execution truth.

## Human Approval
- This contract is read-only and conservative by design.
- Any future use of `setup_id` in runtime gates or decisioning requires a separate approved PR.
