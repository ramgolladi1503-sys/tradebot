# AI Reliability and Decision-Analytics Agent V1 — Agent Review Evidence

mode: PAPER_AND_OFFLINE_SAFE
candidate_id: ai-reliability-agent-v1
decision: SIMULATION_CERTIFIED
live_decision: LIVE_CERTIFICATION_PENDING
reason: implement a bounded evidence-driven investigator and post-market analytics sidecar without broker or runtime decision authority
timestamp: 2026-07-30T23:59:00+05:30
is_order_action: false
broker_api_called: false
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
  - broker order placement, modification or cancellation
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

## Test Evidence

Command:

```bash
PYTHONPATH=. pytest -q
```

Result:

```text
131 passed
```

Suites:

```text
tests/test_ai_reliability_evidence.py
tests/test_ai_reliability_agent.py
tests/test_ai_reliability_analytics.py
tests/test_ai_reliability_integration.py
```

Compilation:

```bash
python -m compileall -q core scripts
```

Result:

```text
PASS
```

## Capability Audit

AST and source-text audit scope:

```text
core/ai_reliability_agent/*.py
```

Result:

```text
Python files scanned: 9
Forbidden findings: 0
```

Confirmed absent:

- Kite and broker imports;
- execution-engine and execution-router imports;
- order placement, modification and cancellation calls;
- subprocess calls;
- shell execution;
- `eval`;
- `exec`.

## Certification Evidence

Command:

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

## Hallucination-Control Evidence

The implementation does not claim that a language model can never hallucinate. It constrains what hallucinated output can accomplish.

Certified in simulation:

- malformed model actions terminate the run;
- unknown tools do not execute;
- live write tools do not execute;
- missing evidence cannot confirm a finding;
- deterministic facts without assertions cannot confirm;
- false assertions are rejected;
- rejected findings remain auditable;
- unsupported trade explanations remain hypotheses or insufficient evidence;
- rejected target touches remain unverifiable without executability evidence;
- model output has no broker or TradeBot mutation authority.

## Behavioral Simulation

A synthetic session included:

- an actual executed trade with a stop outcome;
- a correct non-executable rejection;
- a later-executable missed candidate;
- a selected fallback candidate with a hypothetical target.

The final verdict was deliberately:

```text
PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES
```

This demonstrates that a favorable later outcome does not excuse degraded truth at approval.

## Certification Boundaries

Certified:

- component contracts;
- unit behavior;
- behavioral integration;
- evidence integrity and redaction;
- live read-only tool boundary;
- deterministic finding verification;
- post-market scope separation;
- simulation verdict behavior.

Not certified:

- real live-market operation;
- auth and feed behavior in the next market session;
- broker connectivity;
- multi-hour supervisor stability;
- profitability or structural edge;
- unique causal explanations;
- production deployment readiness.

## Live Certification Requirements

`LIVE_CERTIFIED` remains prohibited until a real session proves:

1. lineage and event artifacts are present and valid;
2. zero invalid JSON rows;
3. zero selected candidates use stale, fallback or recovered-fallback truth;
4. zero unexplained candidate disappearances;
5. all blocked candidates have reasons;
6. all selected and executed records have stable identities;
7. every actual trade joins to candidate lineage;
8. approved candidates have terminal or explicitly open status;
9. evidence-chain verification passes;
10. TradeBot runtime logic remained frozen during observation;
11. the final operational verdict is `PIPELINE_TRUTHFUL_AND_OPERATIONAL`.

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
