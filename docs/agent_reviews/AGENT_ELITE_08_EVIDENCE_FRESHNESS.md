# AGENT-ELITE-08 — Evidence Auditor Runtime Artifact Freshness Guard

mode: REVIEW
candidate_id: AGENT-ELITE-08-EVIDENCE-AUDITOR-RUNTIME-ARTIFACT-FRESHNESS-GUARD
decision: review_pending
reason: artifact_freshness_guard_static_evidence
source: docs/agent_reviews/AGENT_ELITE_08_EVIDENCE_FRESHNESS.md
timestamp: 2026-05-28T18:20:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #380
Parent: #372
Depends on: #379 / PR #395 / merge commit 48568f1944f9c6ea29766830ed3d599512158b10

## Agent Work Contract

This PR implements AGENT-ELITE-08 only.

The work adds static artifact freshness checks to repo-forensics evidence auditing. It checks whether candidate evidence artifacts include usable freshness metadata and whether latest pointers are valid when provided.

It must not run product runtime code, call brokers, modify broker code, change strategy/ranking formulas, change dashboard/UI behavior, or clean up artifacts.

## Scope Guard

Allowed:

- Add `tools/repo_forensics/artifact_freshness.py`.
- Wire freshness findings into `tools/repo_forensics/evidence_auditor.py` behind `evidence.freshness_gate: true`.
- Add focused tests in `tests/test_repo_forensics_artifact_freshness.py`.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Broker code changes.
- Strategy/ranking formula changes.
- Dashboard/UI changes.
- Artifact cleanup.
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

Question: Does this prove candidate quality?

Answer: No. It proves evidence freshness can be classified. It does not validate strategy edge, ranking quality, or execution quality.

Question: Does this change live artifact writers?

Answer: No. It only inspects existing evidence metadata when the freshness gate is enabled.

Question: What happens when timestamp metadata is absent?

Answer: The artifact receives UNKNOWN freshness.

Question: What happens when the artifact age exceeds the configured threshold?

Answer: The artifact receives STALE freshness.

Question: What happens when a latest pointer targets no file?

Answer: The auditor emits a HIGH artifact_freshness finding.

Question: Why is the gate opt-in?

Answer: To preserve older evidence-auditor contracts while enabling strict freshness checks where configured.

## Hermes Review

The implementation is intentionally additive:

- Adds `ArtifactFreshnessResult`.
- Evaluates timestamp existence and parseability.
- Evaluates artifact source metadata.
- Evaluates latest pointer validity when supplied.
- Evaluates session ID when a session artifact is implied.
- Evaluates generated-at versus consumed-at gap when consumed metadata exists.
- Emits `artifact_freshness` findings only when `evidence.freshness_gate` is enabled.

## GSD Review

Smallest safe implementation:

- Keep freshness logic in a pure helper module.
- Reuse existing `audit_evidence(...)` entry point.
- Keep default evidence-auditor behavior unchanged unless the freshness gate is enabled.
- Add deterministic tests using a pinned configured clock.

Files changed:

- `tools/repo_forensics/artifact_freshness.py`
- `tools/repo_forensics/evidence_auditor.py`
- `tests/test_repo_forensics_artifact_freshness.py`
- `docs/agent_reviews/AGENT_ELITE_08_EVIDENCE_FRESHNESS.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_artifact_freshness.py -q
```

Recommended additional command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_artifact_freshness.py tests/test_candidate_evidence_trace_score.py tests/test_repo_forensics_evidence_auditor.py tests/test_repo_forensics_non_action_evidence.py -q
```

Safety assertions:

- No runtime import of target Tradebot modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard behavior change.
- Broker code is untouched.
- Strategy/ranking formulas are untouched.
- Artifact cleanup is not performed.

## Acceptance Proof

The tests prove:

- Timestamp absence produces UNKNOWN freshness.
- Old artifacts exceed the threshold and produce STALE freshness.
- Latest pointer targets that do not exist produce a HIGH finding.
- Fresh and complete artifact metadata produces no artifact_freshness finding.
- Auditor freshness checks run only when the freshness gate is enabled.

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
