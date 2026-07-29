# PR #743 Agent Review Evidence

mode: PAPER
candidate_id: PR-743-MARKET-EVENT-GRAPH-SHADOW
 decision: ADVISORY_ONLY
reason: Frozen breadth graph is integrated for read-only shadow observation with fail-closed input validation.
timestamp: 2026-07-29T11:45:00Z
is_order_action: false
broker_api_called: false
source: PR_743_AGENT_REVIEW_EVIDENCE

## Agent Work Contract
Implement the frozen market-event graph as a read-only TradeBot candidate generator and connect a fail-closed adapter for completed constituent-breadth event snapshots. Do not change broker calls, order placement, execution permissions, risk limits, option selection, or production certification.

## Scope Guard
Changed scope is limited to the candidate-pool orchestrator, the movement-strategy package, the new live-event adapter, the shadow strategy registry entry, and focused tests. No execution, broker, feed transport, risk, authentication, position sizing, or order-management path is changed.

## High-Risk Path Review
`core/candidate_pool_orchestrator.py` and `strategies/**` are treated as high-risk because they influence candidate production. Review confirms:

- the new generator emits `StrategyCandidate` objects only;
- promotion state remains `ADVISORY_ONLY`;
- the strategy contains no broker or order imports;
- input validation is fail-closed;
- incomplete, unknown, malformed, absent, and stale event evidence emits no candidate;
- default-pool wiring adds observation only and does not make candidates executable;
- existing option confirmation, classification, downgrade, ranking, feed-hold, and execution firewalls remain authoritative.

## Grill Me Review

**Could the adapter invent a signal from raw prices?** No. It accepts only explicitly labelled completed breadth events and never estimates thresholds.

**Could an incomplete current bar trigger?** No. Rows with `completed=False` or `is_completed=False` are rejected.

**Could arbitrary event labels trigger?** No. Labels are restricted to the frozen graph vocabulary.

**Could a row without a timestamp trigger?** No. Positive numeric `ts_epoch` is mandatory.

**Could the strategy auto-execute?** No. It produces a raw advisory candidate and carries explicit shadow/no-auto-execution suppression evidence.

**Does this prove option profitability?** No. The discovery result used underlying returns and contained zero actual option rows.

## Hermes Review
Data lineage is:

`completed constituent-breadth snapshot` → `market_event_graph_live_adapter` → canonical chronological/deduplicated event rows → `StrategyContext.metadata` → frozen graph strategy → raw advisory candidate → existing option-confirmation and ranking layers.

The adapter preserves event timestamps and selected numeric evidence for auditability.

## GSD Review
Implementation is intentionally small and deterministic:

1. canonicalize completed labelled event rows;
2. reject all unsupported input;
3. match exactly the frozen three-event order;
4. require freshness;
5. emit one BUY_CALL advisory candidate;
6. run through the existing default read-only candidate pool.

## QA / Safety Review
Focused tests cover:

- exact graph emits one BUY_CALL advisory candidate;
- nonmatching graph emits nothing;
- absent evidence emits nothing;
- stale evidence emits nothing;
- incomplete, unknown, and timestamp-less rows are rejected;
- canonical history ordering and attachment;
- new generator is present in the default candidate pool;
- emitted candidate explicitly reports `is_order_action is False`.

No execution-path tests were weakened or bypassed.

## Acceptance Proof
Acceptance requires CI success for repository tests, strategy registry verification, code-quality checks, CodeQL, repo forensics, and this Agent Review Evidence Gate. The PR must remain unmerged until required checks complete.

## Runtime Proof Required After Merge
During the next live market session, capture:

- the number of completed constituent-breadth snapshots received;
- adapter status (`READY` or `MISSING_OR_INVALID`);
- canonical event labels and timestamps;
- strategy evaluation count;
- candidate emissions and refusals;
- CE quote freshness, spread, and depth at any emission;
- delayed-entry shadow outcome after the research horizon.

This runtime evidence is observation only and cannot promote the strategy.

## What This PR Does Not Prove
This PR does not prove option profitability, independent out-of-sample certification, multiple-testing robustness, production readiness, execution eligibility, or suitability for automated trading. It does not add a complete live constituent data subscription if the upstream market snapshot does not already supply completed labelled breadth events.

## Human Approval
Human approval is required before merge. Approval authorizes shadow advisory observation only. It does not authorize live order execution or strategy certification.
