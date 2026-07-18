# Opening Range Retest Causal Replay Phase 1

mode: RESEARCH_REPLAY_REVIEW
candidate_id: opening_range_retest_causal_replay_phase1_review
decision: AUDIT_INVALID
reason: Hardening for PR #668 is still in progress, so prior full-ensemble outputs are diagnostic only and not certifying after replay-code changes.
timestamp: 2026-07-18
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/opening_range_retest_causal_replay_phase1.md

**Agent Work Contract**
source_agent: Codex
action: HARDEN_PR
title: Close ORB replay proof-contract and evidence gaps for PR #668
scope: Opening Range Retest replay hardening, certifying artifact structure, independent audit, and final bounded evidence publication only
requested_paths: research/opening_range_retest, scripts/generate_opening_range_retest_causal_replay.py, scripts/audit_opening_range_retest_causal_replay.py, tests/test_opening_range_retest_causal_replay.py, docs/agent_reviews/opening_range_retest_causal_replay_*
allowed_paths: docs/agent_reviews, research/opening_range_retest, scripts/generate_opening_range_retest_causal_replay.py, scripts/audit_opening_range_retest_causal_replay.py, tests/test_opening_range_retest_causal_replay.py, tests/test_opening_range_retest_oracle_reconciliation.py, tests/test_opening_range_retest_merge_certification.py
forbidden_paths: strategies/, core/, config/, broker adapters, runtime execution paths, dashboard, live credentials, shared corpus roots
expected_tests: pytest ORB replay suites, agent review evidence validation, unified CE gates, final bounded artifact audit
acceptance_proof: Two authoritative full-corpus ensembles on one frozen clean commit must converge and the republished bounded artifacts must audit clean.

**Scope Guard**
In scope: research-only ORB replay hardening, shard certification, oracle reconciliation, audit strictness, evidence contract compliance, and final bounded artifact regeneration.
Out of scope: production strategy logic, runtime wiring, broker/risk/feed code, strategy thresholds, live or paper execution behavior, and unrelated preparation branches beyond read-only verification.
Files not touched: strategies/, core/, config/, credentials, runtime live paths, broker code, and shared authoritative corpus roots.

**Grill Me Review**
Weak assumption: prior 12-shard and 13-shard outputs remained certifying after replay code changed.
Failure mode: merged artifacts could agree on candidate hashes while hiding shard-identity drift, dirty-worktree execution, incomplete source universe, or ledger tampering.
Current assessment: not ready until replay identity, source-universe completeness, oracle reconciliation, and independent audit are re-proven on the post-hardening commit.

**Hermes Review**
Boundary status: pass so far on production isolation, because all current work remains under research/docs/tests/scripts surfaces.
Boundary risk: evidence files must not imply production readiness, exact VWAP truth, fills, slippage, or profitability.
Constraint: replay hardening may inspect production strategy outputs but must not edit production strategy files or runtime wiring.

**GSD Review**
Purpose: convert the current ORB PR from narrative replay evidence into certifying, independently auditable replay proof.
Files changed so far: ORB replay package, generator/audit scripts, replay tests, bounded ORB artifacts, and this review file.
Evidence so far: local ORB suites pass, prior ensemble A/B matched on published hashes before this hardening pass, and current PR gates identify exact evidence and test-reality gaps.
Risks: certifying merge hardening and final rerun are still pending; this document is intentionally not a final acceptance verdict yet.
Next PR action: integrate merge-owner hardening, rerun authoritative ensembles, republish artifacts, rerun all local gates, then update this review to final READY or explicit failure.

**QA / Safety Review**
Safety boundary: read-only replay only, no order placement, no broker calls, no live execution permission, no write into authoritative corpus roots.
Current proof gaps: execution identity fields, source-universe completeness, stricter shard merge, and repository evidence contract compliance are not all closed on the current PR head.
Test-reality gap: `tests/test_opening_range_retest_causal_replay.py` triggered Minerva fake-confidence rules and is being hardened to behavior proof.

**Acceptance Proof**
Current status: not yet satisfied.
Required final proof: one frozen clean commit, dirty-worktree rejection verified, shard completeness verified, oracle reconciliation upgraded to full temporal identity, independent artifact audit passes, and both authoritative full-corpus ensembles converge on candidate and canonical summary hashes after hardening.

**Runtime Proof Required After Merge**
Required after merge: rerun the authoritative ORB replay from the merged main branch, re-audit bounded artifacts, and confirm the merged branch still produces the certifying verdict on a clean worktree.
Not proven yet: runtime behavior after merging into `main`, exact VWAP truth, option execution truth, slippage/fill truth, profitability, paper readiness, or live readiness.

**What This PR Does Not Prove**
This PR does not prove broker safety, live execution safety, exact VWAP provenance, option quote/depth truth, fills, slippage, profitability, paper readiness, or production readiness.
This PR also does not prove that the stale historical four-strategy manifest can still be regenerated byte-for-byte from today’s live source roots.

**Human Approval**
Human approval required before merge because the PR changes certifying replay evidence semantics and repository-published bounded artifacts.
Current merge recommendation: do not merge PR #668 until the hardening rerun and final independent audit complete.
