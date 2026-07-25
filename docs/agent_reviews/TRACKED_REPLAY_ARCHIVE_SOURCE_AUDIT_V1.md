mode: RESEARCH_ONLY_SOURCE_AUDIT
candidate_id: tracked_replay_archive_source_audit_v1
decision: TRACKED_REPLAY_ARCHIVE_AUDIT_PENDING_GITHUB_RUNNER_EVIDENCE
reason: The exact tracked replay archive requires safe member inventory, physical-hash verification, independent reconciliation, and conservative authority classification before its prior unresolved-source record can be narrowed.
timestamp: 2026-07-25T23:50:00+05:30
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: runtime/upstox_candidate_replay.zip at frozen SHA-256 4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707 and the merged option-E2E source census

# Tracked Replay Archive Source Audit v1

## Agent Work Contract

- source_agent: ChatGPT
- action: GENERATE_PATCH
- title: Audit the tracked Upstox replay archive as one unique source
- scope: Research-only ZIP integrity, member inventory, deny-boundary enforcement, independent oracle, and evidence publication
- allowed_paths: The focused archive-audit package, focused tests, this review, generated evidence, Code Excellence reports, and one temporary evidence workflow
- forbidden_paths: Strategy runtime, broker, order, execution, feed, risk, dashboard, outcomes, P&L, replay execution, WFA, holdout evaluation, and live or paper configuration
- expected_tests: Focused archive security tests plus repository-required checks
- acceptance_proof: Exact archive hash, safe member inventory, primary-oracle agreement, deterministic evidence, matching sidecars, and zero execution authority

## Scope Guard

This work audits only the repository-tracked `runtime/upstox_candidate_replay.zip`. It does not inspect the Mac-only execution trace or claim that the 27 declared local roots have been exhausted. It does not extract members into the repository or execute the replay.

## Grill Me Review

Archive determinism does not establish signal authority. Path names do not establish strategy ownership, and replay inputs do not become canonical datasets merely because they are parseable. Any signal-like member remains non-canonical without implementation, parameter, dataset, temporal, split, freeze, and contamination authority.

## Hermes Review

The primary inspector owns safe member handling and conservative disposition. An independent oracle recomputes the physical hash, ZIP validity, member-name manifest, member count, and safety flags without consuming the primary decision object. Disagreement fails the evidence build.

## GSD Review

The implementation is deliberately narrow: one tracked archive, one frozen physical hash, one source-audit package, one focused test file, and one temporary evidence workflow. No generic source framework or second authority-closure engine is introduced.

## QA / Safety Review

The archive is opened read-only. Absolute paths, traversal, backslashes, symlinks, special files, encrypted members, duplicate names, and case collisions fail closed. Outcome- or P&L-bearing members are recorded by metadata only and are not opened. No member is extracted into a worktree.

## Acceptance Proof

Publication remains pending the GitHub-runner inspection of the exact tracked binary. The final review will replace this paragraph with actual archive size, member counts, dispositions, semantic hashes, focused tests, exact-head checks, and Code Excellence evidence.

## Runtime Proof Required After Merge

None. This audit creates no runtime path and grants no execution authority.

## What This PR Does Not Prove

This work does not prove a canonical signal source, a canonical dataset source, strategy correctness, dataset-version authority, parameter authority, contamination clearance, profitability, replay validity, WFA validity, paper readiness, or live readiness. It does not complete the local source search.

## Human Approval

Human approval remains required before any replacement-ledger generation or later authority decision. The temporary evidence workflow must be removed before publication.
