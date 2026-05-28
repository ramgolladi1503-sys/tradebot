# AGENT-ELITE-02 — Atlas Candidate Lifecycle Trace Contract

mode: REVIEW
candidate_id: AGENT-ELITE-02-ATLAS-CANDIDATE-LIFECYCLE-TRACE
decision: review_pending
reason: atlas_evidence_only_candidate_lifecycle_trace_contract
timestamp: 2026-05-28T11:30:00Z
source: docs/agent_reviews/AGENT_ELITE_02_ATLAS_CANDIDATE_TRACE.md
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #374
Parent: #372
Depends on: #373 / PR #389 / merge commit ce37b6b280fb28805ef81b0f3774fd10602b13b8

## Agent Work Contract

This PR implements AGENT-ELITE-02 only.

The work adds an evidence-only candidate lifecycle trace contract for Atlas. It validates supplied candidate records across generation, finalization, scoring, ranking, data-quality, gatekeeper, risk, final decision, and evidence-output stages.

It must not read live runtime state, import target Tradebot runtime modules, call brokers, place orders, change strategy behavior, change ranking formulas, or change dashboard behavior.

## Scope Guard

Allowed:

- Add `tools/repo_forensics/candidate_trace.py`.
- Add focused tests in `tests/test_repo_forensics_candidate_trace.py`.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Live order behavior.
- Strategy/ranking behavior changes.
- Dashboard/UI changes.
- Broad repo-forensics refactor.
- Test skip/xfail.

## High-Risk Path Review

This PR adds static/evidence-only repo-forensics tooling.

High-risk Tradebot paths intentionally unchanged:

- `core/kite_client.py`
- `core/execution_engine.py`
- `core/execution_router.py`
- `core/risk_engine.py`
- `core/orchestrator.py`
- `strategies/`
- `dashboard/`
- `config/`

The validator accepts already-collected evidence records and does not import or execute target runtime code.

## Grill Me Review

Question: Does this prove live candidate quality?

Answer: No. It proves only that supplied evidence records contain a complete lifecycle trace.

Question: Could a candidate pass without risk proof?

Answer: No. If `final_decision` exists without `risk_evaluated`, the report emits `risk_before_execution_not_proven` as a HIGH finding.

Question: Could ranking be present but ignored?

Answer: The contract flags `ranking_not_consumed` when a ranked candidate reaches final decision without rank reference or explicit `rank_consumed=true`.

Question: Could missing candidate IDs hide trace breaks?

Answer: No. Records without `candidate_id` are hard failures.

## Hermes Review

The contract is intentionally narrow:

- Normalizes known Tradebot flow aliases into canonical lifecycle stages.
- Builds deterministic per-candidate trace objects.
- Tracks missing stages as UNKNOWN.
- Tracks unsafe final-decision conditions as HIGH.
- Renders a markdown report for review.

## GSD Review

Smallest safe implementation:

- Add immutable dataclasses for findings, traces, and report.
- Provide data-only builder: `build_candidate_lifecycle_trace_report(records)`.
- Provide deterministic renderer: `render_candidate_lifecycle_trace_report(report)`.
- Add tests for complete trace, missing candidate ID, missing stage, ranking not consumed, risk-before-decision, unknown stage, and rendering.

Files changed:

- `tools/repo_forensics/candidate_trace.py`
- `tests/test_repo_forensics_candidate_trace.py`
- `docs/agent_reviews/AGENT_ELITE_02_ATLAS_CANDIDATE_TRACE.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_candidate_trace.py -q
```

Recommended additional command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_runtime_wiring.py tests/test_repo_forensics_candidate_trace.py -q
```

Safety assertions:

- No runtime import of target modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard changes.

## Acceptance Proof

The tests prove:

- Known Tradebot flow aliases normalize into canonical candidate lifecycle stages.
- Complete supplied candidate records pass.
- Missing `candidate_id` fails hard.
- Missing lifecycle stages become UNKNOWN, not fake PASS.
- Ranked candidates whose final decision has no rank reference fail as `ranking_not_consumed`.
- Final decision without risk stage fails as `risk_before_execution_not_proven`.
- Unknown stages are reported as UNKNOWN.
- Rendered report includes a clear verdict.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is an evidence-only trace contract.

Future PRs can wire this validator into repo-forensics reports or runtime evidence checks, but this PR intentionally does not do that wiring.

## What This PR Does Not Prove

- Does not prove live startup succeeds.
- Does not prove candidate generation correctness.
- Does not prove ranking formula quality.
- Does not prove broker readiness.
- Does not prove profitability.
- Does not prove dashboard accuracy.
- Does not prove EDGE-98 historical dataset behavior.

## Human Approval

Required before merge.
