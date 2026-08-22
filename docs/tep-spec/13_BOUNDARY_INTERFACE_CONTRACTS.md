# TEP v1 — Boundary Interface Contracts

Status: DRAFT
Version: 1.0.0-draft
Normative: Yes

Repairs Phase-0 finding F-003. These are semantic interfaces, not language-specific APIs.

## IF-MISSION-001 — AdmitMission
Caller: application/operator API. Owner: Mission Engine. Requirements: REQ-MISSION-001/002.
Input: mission definition ref/hash, configuration refs, requested authority context.
Output: MissionInstance ID or typed validation rejection.
Precondition: definition/schema resolvable.
Postcondition: CREATED/VALIDATING state durably recorded.
Idempotency: same admission key + same definition returns same instance or explicit duplicate disposition.

## IF-SCHED-001 — ComputeRunnable
Caller: supervisor/event loop. Owner: TBOS Scheduler. Requirements: REQ-SCHED-001/002.
Input: durable mission/task snapshot/event wake.
Output: ordered runnable task IDs plus derived mission state.
Mutation: scheduler may commit scheduling/lease intent only; no domain side effects.

## IF-TASK-001 — AcquireExecutionLease
Owner: TBOS. Requirements: REQ-STATE-001/003.
Input: task ID, expected fingerprint, worker/handler identity, lease duration.
Output: lease or conflict/stale rejection.
Idempotency: same valid active owner may renew; conflicting owner rejected.

## IF-AUTH-001 — EvaluateAuthority
Owner: Authority Service. Requirements: REQ-AUTH-001/002/003.
Input: capability, mission/task, actor, exact target fingerprint, requested scope, current dependency refs.
Output: ALLOW/DENY with decision ID, constraints and expiry.
No authority is inferred from credentials/tool availability.

## IF-WORKER-001 — ExecuteBoundedTask
Owner: Worker Manager. Requirements: REQ-WORKER-001/002/003.
Input: execution envelope containing exact task fingerprint, allowed/prohibited scope, resource budget and output schema.
Output: immutable WorkerExecution result/artifact refs.
Worker cannot transition task to SUCCEEDED directly.

## IF-VALIDATE-001 — ValidateExecution
Owner: capability/domain validator. Requirements: REQ-WORKER-002, REQ-EVID-001.
Input: task contract, execution result, required authority/source/evidence context.
Output: validated result classification and evidence refs.
Producer assertion is not sufficient validation.

## IF-EVENT-001 — AppendEvent
Owner: Event/State subsystem. Requirements: REQ-EVENT-001.
Input: event ID/idempotency key, type, subject, causal refs, payload schema/version.
Output: committed event offset/ref.
Duplicate idempotency key is non-duplicating.

## IF-GIT-001 — ResolveRepositoryAuthority
Owner: Git Service. Requirements: REQ-GIT-001.
Input: repository/ref/worktree candidate.
Output: exact remote/local SHA, cleanliness/provenance facts, divergence, protected status where available.
Read-only.

## IF-GH-001 — ReadPRSnapshot
Owner: GitHub Service. Requirements: REQ-GH-001.
Input: repository + PR number.
Output: exact state/head/base/metadata/review/check linkage snapshot with observed time.
Read-only.

## IF-CI-001 — ObserveCI
Owner: CI Service. Requirements: REQ-CI-001/002.
Input: exact candidate SHA/PR and required-check policy.
Output: WAITING, PASS, CANDIDATE_FAILURE, BASELINE_FAILURE, ENVIRONMENT_FAILURE, EXTERNAL_FAILURE, POLICY_FAILURE or UNKNOWN with evidence refs.
Pending CI MUST NOT imply repair.

## IF-MERGE-001 — EvaluateAndMerge
Owner: Merge Service. Requirements: REQ-MERGE-001/002.
Input: exact PR/candidate fingerprint and authority decision.
Behavior: refresh main/head/base/checks/reviews/dependencies; reject drift; serialize; merge only if every frozen gate passes.
Output: merge SHA or typed non-merge verdict. Evidence includes JIT snapshot.

## IF-CLEAN-001 — EvaluateDeletion
Owner: Cleanup Service. Requirements: REQ-CLEAN-001.
Input: exact local target plus repository/evidence/runtime mappings.
Output: SAFE_DELETE_CANDIDATE or PRESERVE with predicate evidence. Evaluation alone performs no deletion.

## IF-EVID-001 — SealEvidence
Owner: Evidence Service. Requirements: REQ-EVID-001/002.
Input: artifact refs/hashes, claim, producer, validator, source/data authority, limitations.
Output: immutable EvidenceRecord ref or rejection.

## IF-KNOW-001 — QueryKnowledge
Owner: Knowledge Service. Requirements: REQ-KNOW-001.
Input: scoped query and freshness/provenance constraints.
Output: facts/findings with source refs and confidence/freshness metadata.
Output cannot be used as an AuthorityDecision.

## IF-LIVE-001 — StartReadOnlyObservation
Owner: Live Observation Service. Requirements: REQ-LIVE-001..004.
Input: exact source SHA, dated launch plan, storage refs, market/session, read-only authority decision.
Output: observer/session identity and launch evidence or typed rejection.
Precondition: broker/order/paper/live execution authorities remain false unless unrelated separately frozen policy exists; this interface never widens them.

## IF-RES-001 — EvaluateResearchGate
Owner: Research Validator. Requirements: REQ-RES-001..004.
Input: frozen candidate/spec, data authority, gate type and evidence.
Output: governed gate verdict limited to that gate. No lower gate implies structural-edge certification.

## Interface evolution

Breaking semantic changes require specification/ADR change. M1 may choose language-level signatures/serialization but MUST preserve these ownership, authority, idempotency and result semantics.