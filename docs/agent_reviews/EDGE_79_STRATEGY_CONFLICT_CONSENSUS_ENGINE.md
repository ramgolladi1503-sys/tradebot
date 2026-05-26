# EDGE-79 Strategy Conflict and Consensus Engine Agent Review

mode: REVIEW
candidate_id: edge_79_strategy_conflict_consensus_engine
decision: review_ready
reason: pure_strategy_conflict_consensus_tests_docs
timestamp: 2026-05-26T07:45:00Z
source: edge79_consensus_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

EDGE-79 introduces a pure read-only strategy conflict and consensus layer over CandidateIntent values.

The implementation creates deterministic consensus decisions and blocks ambiguous candidate groups with explicit blockers.

## Work contract

EDGE-79 covers consensus only.

It does not add NoTradeOracle, dashboard work, ranking, scoring, paper journal writes, new strategy families, or runtime wiring.

## Scope guard

- Same instrument and same direction group can become ready consensus.
- Opposing CALL and PUT groups for the same instrument are blocked.
- Duplicate family candidates for the same instrument and direction are blocked.
- Pool-ineligible candidates remain blocked.
- Non-entry candidates remain blocked.
- Unsupported directions remain blocked.

## High-risk path review

The high-risk path is conflicting strategy output becoming usable as if it had agreement.

Controls:

- Candidates are first passed through the existing CandidateIntent pool validator.
- Conflict checks are grouped by instrument.
- Direction conflicts block the whole instrument group.
- Duplicate family conflicts block repeated same-family signals.
- Report payloads remain non-action and read-only.

## Grill Me review

Question: Can this PR create runtime side effects?

Answer: No. It only returns read-only dataclass reports.

Question: Can opposing strategy directions pass as consensus?

Answer: No. Opposing direction groups for the same instrument produce `consensus_direction_conflict`.

Question: Does this PR rank or score strategies?

Answer: No. It only checks agreement and blockers.

## Hermes review

The public contract is stable and explicit:

- `build_strategy_conflict_consensus(...)`
- `StrategyConsensusReport.to_payload()`
- `StrategyConsensusDecision.to_payload()`

The schema exposes readiness, blockers, warnings, decisions, pool report, and non-action fields.

## GSD review

The PR keeps the work narrow:

- one core module
- one focused test file
- one implementation doc
- one agent-review evidence file
- TODO update that removes EDGE-79 from remaining work

## QA / safety review

Focused tests cover:

- ready consensus for same instrument and same direction across different families
- direction conflict for same instrument
- separate instruments not conflicting with each other
- duplicate family conflict
- pool-ineligible candidate preservation
- non-entry candidate blocking
- empty input fail-closed behavior
- pool report preservation and metadata guarantees

## Runtime Proof Required After Merge

After merge, runtime proof is still required before any later PR wires this report into broader flow behavior.

The proof must show consensus blocks conflicts and does not bypass feed, option, NoTrade, or executable-quality gates.

## What This PR Does Not Prove

This PR does not prove live profitability, live readiness, paper-truth expectancy, NoTrade quality, or final executable quality.

Those belong to later roadmap items.

## Human Approval

Human review is required before any later PR changes how consensus decisions are used by broader runtime or review flows.

## Acceptance proof

Command:

`PYTHONPATH=. python -m pytest tests/test_edge_79_strategy_conflict_consensus.py`

Expected result:

- focused EDGE-79 tests pass
- conflicts produce explicit blockers
- same-direction consensus remains ready
- no runtime or dashboard change
