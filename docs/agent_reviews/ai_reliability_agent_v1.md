# AI Reliability and Decision-Analytics Agent V1 — Agent Review Evidence

mode: PAPER_AND_OFFLINE_SAFE
candidate_id: ai-reliability-agent-v1
decision: SIMULATION_CERTIFIED
live_decision: LIVE_CERTIFICATION_PENDING
reason: implement a bounded evidence-driven investigator and post-market analytics sidecar without broker or runtime decision authority
timestamp: 2026-07-30T23:59:00+05:30
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/ai_reliability_agent_v1.md

## Agent Work Contract

```text
source_agent: ChatGPT GitHub agent
operation: IMPLEMENT_BOUNDED_AI_RELIABILITY_AGENT_V1
base_commit: 17262b4b6a42eb09d4d508bfdf6fe0d649ee32af
branch: feature/ai-pipeline-reliability-agent-v1
draft_pr: 760
scope:
  - define exact agent, evidence, finding, assertion, analytics and certification contracts
  - consume existing TradeBot runtime events, candidate lineage, candidate summaries and trade logs
  - add deterministic trigger-driven live observation
  - add allow-listed read-only diagnostic tools
  - add a strict structured OpenAI reasoner
  - add deterministic finding verification
  - add redacted SHA-256 chained evidence storage
  - add actual, hypothetical, counterfactual and unresolved outcome separation
  - add post-market candidate autopsies, rejection analysis, score calibration and segment analytics
  - add component and simulation certification
allowed_paths:
  - core/ai_reliability_agent/**
  - scripts/run_ai_reliability_agent.py
  - tests/test_ai_reliability_*.py
  - docs/architecture/ai_reliability_agent_v1.md
  - docs/test-reports/ai_reliability_agent_v1_certification.*
  - docs/agent_reviews/ai_reliability_agent_v1.md
forbidden_paths:
  - main.py
  - core/orchestrator.py
  - core/auth*.py
  - core/market_data*.py
  - core/kite*.py
  - core/execution*.py
  - core/risk*.py
  - strategies/**
  - config/**
  - dashboard/**
forbidden_capabilities:
  - broker order creation, update or cancellation
  - runtime restart or reconnect
  - strategy, threshold, score or risk mutation
  - candidate promotion or suppression
  - shell or subprocess execution
  - automatic repair, merge or deployment
acceptance:
  - unknown tools fail closed
  - live write tools are blocked
  - evidence is redacted and tamper-evident
  - deterministic findings require evidence IDs and assertions
  - contradictory assertions are rejected
  - unsupported evidence produces insufficient evidence
  - actual and counterfactual outcomes never share realized-performance authority
  - rejected theoretical winners are not automatically called missed opportunities
  - option attribution respects CE/PE direction
  - selected degraded candidates fail the session verdict closed
  - no existing runtime trading behavior is modified
```

## Scope Guard

This PR is an isolated sidecar implementation. It reads existing artifacts and writes only its own evidence and report artifacts.

It does not:

- subscribe to market feeds;
- call Kite or another broker;
- change TradeBot authentication;
- create strategy candidates;
- alter candidate gates;
- rank opportunities;
- approve trades;
- route execution;
- change a position;
- patch or restart TradeBot.

## Implemented Components

### Contracts

Defines operating modes, decisions, severity, claim kinds, finding status, session verdicts, certification levels, rejection verdicts, decision/outcome classes, outcome kinds/scopes and contributor taxonomy.

### Evidence ledger

Provides recursive redaction, canonical serialization, UUID evidence IDs, prior-hash linkage, current-row SHA-256, thread-safe append, best-effort fsync and tamper verification.

### Tool registry

Provides allow-listed tools with declared read-only authority. Unknown tools fail with `UNKNOWN_TOOL`; write tools in live mode fail with `LIVE_MODE_WRITE_TOOL_BLOCKED`.

### Reasoner

Uses strict structured model output. The model can request one diagnostic tool, propose one structured finding or stop. The API key remains outside the request body. Model narrative is never accepted as evidence.

### Verifier

Confirms only findings whose evidence exists and whose assertions pass deterministic operators. It rejects contradictions and returns insufficient evidence when required evidence is absent.

### Supervisor

Polls deterministic triggers, deduplicates trigger fingerprints and invokes the bounded agent only for unseen conditions.

### Analytics

Builds funnel, rejection, candidate-autopsy, decision/outcome, rejection-verdict, score-calibration and segment reports. It joins actual trade-log records without promoting rejected candidates into real trades.

### Certification

Runs deterministic security, evidence, behavioral and analytics gates and emits machine-readable and human-readable results.

## Exact Exposed Diagnostic Tools

```text
get_artifact_health
analyze_candidate_lineage
query_candidate_lineage
query_runtime_events
```

All four are local and read-only.

## Grill Me Review

### What assumption can silently kill this change?

The largest assumption is that existing runtime lineage and trade-log artifacts are sufficiently complete and semantically stable. The agent cannot recover facts that TradeBot never records. A clean AI report generated from incomplete lineage would be false confidence, so missing rows, unmatched trades, blocked candidates without reasons and generated-versus-observed discrepancies are explicit observability gaps.

### What behavior is claimed but not proven?

A real multi-hour market session has not yet proven:

- authentication and feed behavior under live conditions;
- trigger detection across a full market day;
- actual candidate identity continuity through every runtime stage;
- all real trade-log joins;
- resource consumption and supervisor stability.

Those claims remain `LIVE_CERTIFICATION_PENDING`.

### What could fail even when focused tests pass?

- upstream schemas may drift;
- strategy or execution code may omit required IDs;
- a real trade-log may use identifiers unavailable in lineage;
- live artifacts may be written partially during reads;
- an operator may start the supervisor with the wrong session date;
- an external model request may fail or time out.

V1 handles missing and malformed evidence fail-closed but cannot prove complete upstream instrumentation before a real campaign.

### Grill Me verdict

```text
NO_FAKE_LIVE_CERTIFICATION
SIMULATION_SCOPE_SUPPORTED
REAL_SESSION_PROOF_REQUIRED
```

## Hermes Review

### In-scope files

```text
core/ai_reliability_agent/**
scripts/run_ai_reliability_agent.py
tests/test_ai_reliability_*.py
docs/architecture/ai_reliability_agent_v1.md
docs/test-reports/ai_reliability_agent_v1_certification.*
docs/agent_reviews/ai_reliability_agent_v1.md
```

### Out-of-scope files confirmed untouched

```text
main.py
core/orchestrator.py
core/auth.py
core/market_data.py
core/execution_engine.py
core/execution_router.py
core/risk_engine.py
strategies/**
config/**
dashboard/**
```

### Boundary result

- No broker client dependency introduced.
- No order authority introduced.
- No runtime strategy or gate behavior changed.
- No risk or ranking mutation introduced.
- No automatic patch, merge, deployment, restart or reconnect action introduced.

### Hermes verdict

```text
SCOPE_PASS
SAFETY_BOUNDARY_PASS
UNRELATED_RUNTIME_FILES_UNTOUCHED
```

## GSD Review

### Purpose

Replace indefinite source-code auditing with a bounded live-observation and post-market evidence workflow.

### Files changed

- nine agent package modules;
- one CLI;
- four focused test suites;
- architecture, certification and agent-review evidence documents.

### Delivery evidence

```text
focused_tests: 131 passed
python_compilation: PASS
component_certification: 10/10 passed
capability_scan: 9 files, 0 forbidden findings
simulation_verdict: SIMULATION_CERTIFIED
live_verdict: LIVE_CERTIFICATION_PENDING
```

### Risks

- no real-session evidence yet;
- upstream artifact completeness remains a dependency;
- causal trade explanations remain intentionally non-authoritative;
- repository CI must pass on the final head.

### Next action

Run a controlled read-only market session, finalize the report, and evaluate the live acceptance gates without changing runtime code during the session.

### GSD verdict

```text
DELIVERY_COMPLETE_FOR_V1_COMPONENT_SCOPE
DO_NOT_MERGE_UNTIL_FINAL_CI_AND_LIVE_CAMPAIGN_DECISION
```

## QA / Safety Review

### Test coverage

- evidence redaction and hash-chain integrity;
- concurrent evidence appends;
- every assertion operator and negative assertion cases;
- unknown-tool and live-write rejection;
- model-action parsing and API-key isolation;
- tool exceptions and budgets;
- actual/hypothetical/counterfactual separation;
- rejected-target hindsight protection;
- direction-aware option attribution;
- trigger detection and deduplication inputs;
- session finalization and verdict precedence;
- actual trade-log joining and unmatched-trade detection.

### Safety negatives

- unknown tools cannot execute;
- registered write tools cannot execute in live-observe mode;
- unsupported deterministic findings cannot confirm;
- selected degraded candidates cannot receive a truthful session verdict;
- rejected candidates are not promoted into actual trades;
- missing lineage invalidates the session.

### Capability audit

```text
Python files scanned: 9
broker or execution imports: 0
broker order action calls: 0
shell or subprocess capability: 0
dynamic eval/exec capability: 0
```

### QA / Safety verdict

```text
FOCUSED_QA_PASS
NEGATIVE_SAFETY_PATHS_PASS
LIVE_SOAK_NOT_YET_PROVEN
```

## Acceptance Proof

Command:

```bash
PYTHONPATH=. pytest -q
```

Result:

```text
131 passed
```

Compilation:

```bash
python -m compileall -q core scripts
```

Result:

```text
PASS
```

Certification:

```bash
PYTHONPATH=. python scripts/run_ai_reliability_agent.py certify \
  --output-dir .runtime/ai_reliability_agent/certification
```

Result:

```text
EVIDENCE_REDACTION: PASS
IMMUTABLE_HASH_CHAIN: PASS
LIVE_READ_ONLY_BOUNDARY: PASS
SUPPORTED_FINDING_CONFIRMED: PASS
UNSUPPORTED_FINDING_REJECTED: PASS
DECISION_OUTCOME_SEPARATION: PASS
UNTRUSTWORTHY_EMISSION_FAILS_CLOSED: PASS
OUTCOME_SCOPE_SEPARATION: PASS
REJECTED_TARGET_NOT_AUTOMATIC_MISSED_OPPORTUNITY: PASS
DIRECTION_AWARE_OPTION_ATTRIBUTION: PASS

10/10 passed
SIMULATION_CERTIFIED
LIVE_CERTIFICATION_PENDING
```

A synthetic session deliberately included a selected fallback candidate. The final verdict correctly failed closed as:

```text
PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES
```

## Runtime Proof Required After Merge

The implementation does not require merge to run, and this PR remains draft. Before any live-certification claim, a controlled branch run must produce:

1. a session manifest;
2. a complete candidate-lineage artifact;
3. runtime events;
4. trade-log joins for actual outcomes;
5. a valid evidence hash chain;
6. zero invalid JSON rows;
7. zero selected stale/fallback/recovered candidates;
8. zero unexplained candidate disappearances;
9. reasons for every blocked candidate;
10. stable IDs for selected and executed records;
11. terminal or explicitly open status for approved candidates;
12. a final `PIPELINE_TRUTHFUL_AND_OPERATIONAL` verdict.

The runtime observation must occur without patching TradeBot during the session.

## What This PR Does Not Prove

This PR does not prove:

- live authentication or feed correctness;
- broker connectivity;
- multi-hour market-session stability;
- profitable strategy expectancy;
- structural market edge;
- correctness of strategy thresholds;
- unique causality for a target or stop;
- production deployment readiness;
- that a language model can never emit a false statement.

It proves a narrower property: unsupported model output cannot become a confirmed deterministic finding through the implemented verifier, and the agent has no registered TradeBot or broker mutation authority.

## Human Approval

Required human decisions:

- whether to run the live supervisor;
- which branch and session date to observe;
- whether a P0/P1 finding warrants a separate repair campaign;
- whether a repair proposal may be implemented on an isolated branch;
- whether any later PR may be merged or deployed.

No human approval has been granted for:

- production deployment;
- automatic order authority;
- automatic repairs;
- automatic restart or reconnect;
- live certification;
- merging PR #760.

## Final Review Verdict

```text
IMPLEMENTATION: COMPLETE FOR V1 SCOPE
FOCUSED TESTS: PASS (131)
COMPILATION: PASS
CERTIFICATION GATES: PASS (10/10)
CAPABILITY AUDIT: PASS
SIMULATION CERTIFICATION: GRANTED
LIVE CERTIFICATION: PENDING
MERGE AUTHORITY: NOT GRANTED
```

This PR must remain draft and unmerged until repository CI completes and a controlled live observation campaign is assessed separately.
