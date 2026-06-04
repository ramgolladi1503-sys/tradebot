# Fresh FeedTruth Audit Proof Pack

mode: REVIEW
candidate_id: PR-FRESH-FEEDTRUTH-AUDIT-PROOF-PACK
decision: add_read_only_audit_proof_pack
reason: The feed truth audit harness needs deterministic proof-pack evidence showing the old bad executable leak still fails, the fixed blocked candidate passes, and live fresh evidence passes without changing runtime behavior.
timestamp: 2026-06-05T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/fresh-feedtruth-audit-proof-pack.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (read-only proof pack + deterministic proof fixtures + CLI)
title: Fresh FeedTruth Audit Proof Pack
scope: create a deterministic proof pack that demonstrates old-bad feedtruth evidence fails while fixed blocked and live fresh evidence pass, without changing runtime behavior
requested_paths:
  - scripts/run_feedtruth_audit_proof_pack.py
  - tests/test_feed_truth_audit_proof_pack.py
  - tests/fixtures/feedtruth_audit/old_bad_unknown_top_executable.jsonl
  - tests/fixtures/feedtruth_audit/new_good_unknown_blocked_candidate.jsonl
  - tests/fixtures/feedtruth_audit/live_fresh_good_candidate.jsonl
  - tests/fixtures/feedtruth_audit/*.runtime.json
  - docs/feedtruth_audit_proof_pack.md
  - docs/agent_reviews/fresh-feedtruth-audit-proof-pack.md
allowed_paths:
  - scripts/run_feedtruth_audit_proof_pack.py
  - tests/test_feed_truth_audit_proof_pack.py
  - tests/fixtures/feedtruth_audit/*
  - docs/feedtruth_audit_proof_pack.md
  - docs/agent_reviews/*
forbidden_paths:
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/broker*
  - core/order*
  - strategies/*
  - dashboard/*
  - config/*
  - runtime/live*
  - logs/broker*
  - secrets*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv
  - PYTHONPATH=. python scripts/run_feedtruth_audit_proof_pack.py --out-dir /tmp/feedtruth_proof_pack
  - PYTHONPATH=. pytest -q tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr483_changed_paths.txt
acceptance_proof:
  - old bad feedtruth evidence still fails audit
  - fixed blocked candidate evidence passes audit with zero contradictions
  - live fresh executable evidence passes audit with zero contradictions
  - all reports remain read-only and fail closed on mismatch
```

## Scope Guard

- This PR is read-only evidence tooling only.
- It must not call broker APIs, place orders, change execution gates, or alter strategy/ranking/Phase2 behavior.
- It must fail closed when required evidence is missing or contradictory.

## Grill Me Review

- The proof pack must not soften the audit harness or let blocked evidence pass.
- The proof pack must preserve the old bad contradiction as a failure.
- The proof pack must surface read-only flags explicitly in every report.

## Hermes Review

- The proof pack is deterministic and fixture-driven.
- It separates the failing old bad fixture from the passing fixed blocked and live fresh fixtures.
- It writes a clear summary alongside per-case JSON reports.

## GSD Review

- Changes are limited to fixtures, a small CLI wrapper, tests, and docs.
- No production runtime path is modified.

## QA / Safety Review

- The reports remain read-only.
- `read_only=true`, `append=false`, `is_order_action=false`, `broker_api_called=false`, and `live_order_allowed=false` remain enforced in the generated reports.
- `live_order_action=false` and `broker_order_action=false` remain enforced in the generated reports.
- The proof pack exits non-zero if the expected verdicts or contradiction counts do not match.

## Acceptance Proof

- Old bad fixture verdict: `FAIL` with contradiction count `> 0`.
- New fixed blocked fixture verdict: `PASS` with contradiction count `0`.
- Live fresh fixture verdict: `PASS` with contradiction count `0`.
- The CLI writes `summary.md` and one report JSON per fixture.

## Runtime Proof Required After Merge

- Run `python scripts/run_feedtruth_audit_proof_pack.py --out-dir /tmp/feedtruth_proof_pack`.
- Inspect `/tmp/feedtruth_proof_pack/summary.md`.
- Confirm the old bad report still fails and the new fixed/live reports pass.

## What This PR Does Not Prove

- It does not change FeedTruth, execution truth, ranking, candidate generation, Phase2, broker/order behavior, websocket recovery, or dashboard/UI logic.
- It does not prove live trading health.
- It does not authorize any order action.

## Human Approval

This is safe to review as read-only proof tooling only.
