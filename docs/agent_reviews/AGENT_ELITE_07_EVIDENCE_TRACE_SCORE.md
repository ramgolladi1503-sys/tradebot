# AGENT-ELITE-07 — Candidate Evidence Trace Completeness Score

mode: REVIEW
candidate_id: AGENT-ELITE-07-CANDIDATE-EVIDENCE-TRACE-COMPLETENESS-SCORE
decision: review_pending
reason: candidate_evidence_trace_completeness_score
source: docs/agent_reviews/AGENT_ELITE_07_EVIDENCE_TRACE_SCORE.md
timestamp: 2026-05-28T18:00:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #379
Parent: #372
Depends on: #378 / PR #394 / merge commit 6c8d700c85ac6cd009258000846b258dc2e32fc1

## Agent Work Contract

This PR implements AGENT-ELITE-07 only.

The work adds a static candidate evidence trace completeness score so candidate decisions can be audited for complete identity, source, mode, timestamp, data quality, score/rank, reason, risk result, broker/action flags, and final decision.

It must not run product runtime code, call brokers, modify broker code, change strategy/ranking formulas, or change dashboard/UI behavior.

## Scope Guard

Allowed:

- Add `tools/repo_forensics/candidate_evidence_trace.py`.
- Wire the trace score into `tools/repo_forensics/evidence_auditor.py` behind `evidence.trace_completeness_gate: true`.
- Add focused tests in `tests/test_candidate_evidence_trace_score.py`.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Broker code changes.
- Strategy/ranking formula changes.
- Dashboard/UI changes.
- Broad repo-forensics refactor.
- Test skip/xfail.

## High-Risk Path Review

This PR modifies static repo-forensics evidence-audit code only.

High-risk Tradebot paths intentionally unchanged:

- `core/kite_client.py`
- `core/execution_engine.py`
- `core/execution_router.py`
- `core/risk_engine.py`
- `core/orchestrator.py`
- `strategies/`
- `dashboard/`
- `config/`

## Grill Me Review

Question: Does this prove candidate profitability?

Answer: No. It proves candidate evidence is auditable. It does not validate edge, ranking quality, or execution quality.

Question: Does this change ranking or confidence?

Answer: No. It only scores evidence completeness after a candidate decision record exists.

Question: Can evidence be trace-complete without candidate identity?

Answer: No. Candidate identity absence is a hard fail.

Question: Can evidence be trace-complete without broker/action flags?

Answer: No. All four broker/action flags must exist and be false.

Question: Why is the gate opt-in?

Answer: To preserve older evidence-auditor contracts while allowing AGENT-ELITE-07 strict trace scoring where configured.

## Hermes Review

The implementation is intentionally additive:

- Adds `CandidateTraceScore` and `TraceDimensionResult`.
- Scores ten trace dimensions evenly.
- Treats absent candidate identity as a hard fail.
- Treats absent decision rationale as incomplete but not hard-failed.
- Treats absent or non-false broker/action flags as trace-incomplete.
- Emits `candidate_trace` findings when `evidence.trace_completeness_gate` is enabled.

## GSD Review

Smallest safe implementation:

- Keep trace scoring in a pure helper module.
- Reuse existing `audit_evidence(...)` entry point.
- Keep default evidence-auditor behavior unchanged unless trace gate is enabled.
- Add deterministic tests for the acceptance criteria.

Files changed:

- `tools/repo_forensics/candidate_evidence_trace.py`
- `tools/repo_forensics/evidence_auditor.py`
- `tests/test_candidate_evidence_trace_score.py`
- `docs/agent_reviews/AGENT_ELITE_07_EVIDENCE_TRACE_SCORE.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_candidate_evidence_trace_score.py -q
```

Recommended additional command:

```bash
PYTHONPATH=. pytest tests/test_candidate_evidence_trace_score.py tests/test_repo_forensics_evidence_auditor.py tests/test_repo_forensics_non_action_evidence.py -q
```

Safety assertions:

- No runtime import of target Tradebot modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard behavior change.
- Broker code is untouched.
- Strategy/ranking formulas are untouched.

## Acceptance Proof

The tests prove:

- Complete candidate evidence scores 100 and is trace-complete.
- Candidate identity absence hard-fails the trace score.
- Decision rationale absence reduces the score and is flagged.
- Broker/action flag absence prevents trace-complete status.
- Evidence auditor emits candidate trace findings only when the trace gate is enabled.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is static evidence analysis only.

## What This PR Does Not Prove

- Does not prove live startup succeeds.
- Does not prove candidate quality.
- Does not prove ranking formula quality.
- Does not prove broker readiness.
- Does not prove profitability.
- Does not prove dashboard accuracy.
- Does not validate dynamic runtime dispatch.

## Human Approval

Required before merge.
