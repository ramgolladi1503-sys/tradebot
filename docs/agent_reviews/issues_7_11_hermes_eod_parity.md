# Hermes Addendum — Issue 10 EOD Decision-Ledger Parity

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Finding

The observer writes its read-only decision projection to the session-local `candidate_decisions.jsonl`. The advisory producer can read that exact caller-provided path. In session-scoped daily reporting, `load_session_diagnostics` already reads `candidate_decisions.jsonl` and records its resolved path, SHA-256, valid record count, and malformed record count. Separately, `load_session_events` treats `candidate_journal.jsonl` as the only session candidate-intent source. Decision-projection rows therefore remain diagnostic telemetry and do not enter outcome replay.

## Contract

For a stable, newline-terminated observer ledger with valid object rows:

1. The advisory producer and session-scoped EOD diagnostics refer to the same ledger path.
2. Advisory row identifiers equal those in the writer ledger after the existing advisory conversion.
3. EOD telemetry reports the ledger's exact raw-byte SHA-256, valid object count, and malformed count.
4. Decision-projection rows remain diagnostic-only; they do not become trade-intent events or outcome-replay inputs.
5. Missing, malformed, or partial JSONL behavior remains governed by the existing producer and analytics contracts. This test does not certify live-session parity or concurrent-writer atomicity.

## Scope

Test-only contract verification. No production source, candidate generation, ranking, strategy semantics, risk gate, feed gate, execution authority, or output format changes are authorized by this addendum.

## Acceptance proof

A deterministic temporary session ledger with two valid decision rows must produce those same IDs in the advisory payload; the EOD report must identify the same resolved file and raw digest with two valid rows and zero malformed rows; the EOD event count must remain zero when no candidate journal exists.

## Agent Work Contract

Campaign issue contract; see `issues_7_11_campaign_review.md` for the PR-level Hermes/GSD scope and actions.

## Scope Guard

Issue-level design boundary and restrictions are defined above; the consolidated review records the full campaign boundary.

## Grill Me Review

Campaign risk critique and unresolved proof limits are recorded in `issues_7_11_campaign_review.md`.

## Hermes Review

This file is the issue-specific Hermes contract. The consolidated review records the cross-issue architecture review.

## GSD Review

Execution evidence and test limits are recorded in `issues_7_11_campaign_review.md`; this contract alone is not implementation proof.

## QA / Safety Review

Safety boundary and verification limits are recorded in `issues_7_11_campaign_review.md`.

## High-Risk Path Review

See `issues_7_11_campaign_review.md` for the cross-cutting review of feed and orchestrator high-risk paths. This issue contract does not authorize runtime or broker actions.

## Acceptance Proof

Issue-specific acceptance criteria are defined above. Cross-issue executed proof and its limitations are recorded in `issues_7_11_campaign_review.md`.

## Runtime Proof Required After Merge

Runtime proof requirements are recorded in `issues_7_11_campaign_review.md`; offline contract text does not establish runtime parity.

## What This PR Does Not Prove

See the consolidated review for campaign-level limitations. This issue contract does not independently claim live verification.

## Human Approval

This design contract does not represent human approval. The PR remains subject to human review as described in `issues_7_11_campaign_review.md`.
