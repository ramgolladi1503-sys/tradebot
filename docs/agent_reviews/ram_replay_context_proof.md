# RAM Replay Context Proof — Agent Review Evidence

```yaml
mode: docs_and_evidence
candidate_id: ram_replay_context_proof
branch: ram/replay-context-proof
base_ref: origin/main
decision: approve_scoped_replay_context_proof
reason: read_only_evidence_and_policy_propagation_only
timestamp: 2026-07-12T20:54:27Z
is_order_action: false
broker_api_called: false
production_artifacts_written: false
replay_only: true
source: docs/research/replay_context_policy_rerun_final_audit.md
```

## Agent Work Contract

Scope for this PR is limited to replay-context proof infrastructure, isolated replay handoff plumbing, policy propagation, and evidence/audit docs.

Files in scope:

```text
core/candidate_journal.py
core/replay_candidate_handoff_entrypoint.py
core/replay_context_bundle_recorder.py
core/replay_context_recorder.py
core/runtime_candidate_handoff.py
scripts/run_replay_candidate_handoff.py
tests/test_candidate_journal.py
tests/test_replay_candidate_handoff_entrypoint.py
tests/test_replay_context_bundle_recorder.py
tests/test_replay_context_runtime_field_mapping.py
tests/test_stress_replay_data_inventory_report.py
docs/research/*.md
docs/agent_reviews/ram_replay_context_proof.md
```

## Scope Guard

Allowed:

```text
Record replay context evidence.
Propagate explicit OOS, timing, and feed-truth policy inputs.
Write isolated replay handoff and bundle artifacts only under replay output paths.
Add or tighten tests for fail-closed behavior and evidence preservation.
Add and update research/audit docs.
```

Not allowed:

```text
Live trading.
Broker APIs.
Order placement.
Risk gate weakening.
Strategy threshold changes.
Ranking logic changes.
Production runtime artifact overwrites.
Synthetic candidates.
```

## Grill Me Review

Risk: policy inputs could be accepted by the CLI but lost before bundle recording.
Mitigation: tests assert the bundle preserves explicit policy values and provenance markers end-to-end.

Risk: isolated replay output could contaminate production-style runtime files.
Mitigation: default output remains under isolated replay directories; tests assert production artifacts are not overwritten.

Risk: metadata-ready replay could be mistaken for candidate proof.
Mitigation: audits explicitly preserve `BLOCKED_NO_CANDIDATE` when no natural candidate is emitted.

## Hermes Review

The design is consistent with the replay proof contract: the runner carries explicit replay policy inputs, bundle recording preserves them, and evidence remains read-only and fail-closed.

It does not introduce a new live path, broker dependency, or ranking/strategy rewrite.

## GSD Review

This PR improves replay evidence quality by closing a policy-propagation hole and making the bundle recorder truthful about explicit replay context.

It is a narrow hardening step, not a strategy-validation claim.

## QA / Safety Review

Coverage added or updated around:

```text
Isolated replay output routing.
Replay input fail-closed behavior.
Explicit OOS context preservation.
Explicit timing policy preservation.
Explicit feed-truth policy preservation.
Bundle recorder provenance markers.
Candidate/journal persistence isolation.
Quote provenance and age preservation.
```

## Acceptance Proof

Required checks run locally:

```bash
pytest -q tests/test_replay_context_bundle_recorder.py tests/test_replay_candidate_handoff_entrypoint.py tests/test_candidate_journal.py tests/test_edge_79a_s_runtime_candidate_handoff_evidence.py tests/test_replay_context_runtime_field_mapping.py tests/test_stress_replay_data_inventory_report.py
```

Proof obligations:

```text
Explicit replay policy inputs survive into the replay bundle.
Replay output remains isolated.
Production artifacts are not overwritten.
No synthetic candidate is created.
Blocked replay slices remain blocked when no natural candidate exists.
```

## Runtime Proof Required After Merge

A future runtime bundle must be captured from a real candidate-producing replay event when available. That is not proven by this PR.

## What This PR Does Not Prove

This PR does not prove a profitable strategy, live execution readiness, or natural candidate generation for all replay windows. It only proves replay-context evidence and policy propagation for the current proof harness.

## Human Approval

Approved for scoped PR review after CI passes.


## High-Risk Path Review

N/A
