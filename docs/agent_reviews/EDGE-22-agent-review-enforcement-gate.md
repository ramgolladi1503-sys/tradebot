# EDGE-22 — Agent Review Enforcement Gate

## Evidence Contract Fields

- mode: CI_PROCESS
- candidate_id: EDGE-22-agent-review-enforcement-gate
- decision: ENFORCE_AGENT_REVIEW_EVIDENCE_GATE
- reason: Future PRs must include explicit mini-agent review evidence before merge.
- timestamp: 2026-05-21T11:40:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-22-agent-review-enforcement-gate.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: EDGE-22 / PR #175 planned
- Branch: agent-review-enforcement-gate
- Scope: make agent review evidence mandatory for future pull requests.
- Allowed files:
  - scripts/validate_agent_review_evidence.py
  - .github/workflows/agent-review-gate.yml
  - .github/pull_request_template.md
  - docs/agent_reviews/EDGE-22-agent-review-enforcement-gate.md
- Forbidden files:
  - core/orchestrator.py
  - core/auth.py
  - core/kite_depth_ws.py
  - core/execution_engine.py
  - strategies/
  - config/
- Forbidden behaviors:
  - No runtime logic changes.
  - No broker behavior changes.
  - No feed/WebSocket changes.
  - No strategy, scoring, ranking, threshold, or dashboard changes.
- Acceptance tests:
  - Validator fails when no docs/agent_reviews/*.md file is changed.
  - Validator fails when required sections are absent.
  - Validator fails when high-risk files change without High-Risk Path Review.
  - GitHub Actions runs the validator on pull_request events.
- Runtime proof required: none. This PR is CI/process only.

## Scope Guard

Verdict: PASS

Checked:

- No broker placement changes.
- No LIVE mode enablement.
- No strategy/scoring/threshold changes.
- No dashboard changes.
- No credential handling changes.
- No runtime/feed behavior changes.
- No fake runtime proof.

Blocking issues: none.

## Grill Me Review

Verdict: PASS

Questions asked:

1. Is chat discipline enough to enforce the agent architecture?
   - No. It already failed from PR #169 onward.
2. Can this be enforced without touching runtime code?
   - Yes. A CI validator can block PRs that lack agent-review evidence.

Risks found:

1. The gate could block emergency documentation-only PRs.
   - Accepted. Those PRs still need a small agent evidence doc.
2. The gate could become box-ticking.
   - Mitigated by requiring concrete sections including What This PR Does Not Prove and Human Approval.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. The validator is isolated under scripts/ and has no runtime imports.
2. The workflow is limited to pull_request events and read-only permissions.

Long-term maintainability:

1. Required sections are plain strings, easy to update.
2. High-risk path detection is explicit and conservative.

## GSD Review

Verdict: PASS

Execution plan:

1. Add validator script.
2. Add pull_request workflow.
3. Update PR template.
4. Add this evidence doc so the enforcement PR passes its own rule.

Evidence required:

1. Changed files show validator, workflow, PR template, and evidence doc only.
2. CI must run the agent-review gate on this PR.

## QA / Safety Review

Tests required:

1. Run validator against this branch:

```bash
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

2. Confirm GitHub Actions runs Agent Review Evidence Gate.

Safety checks:

1. No runtime code changed.
2. No secrets or operational credentials introduced.

## High-Risk Path Review

Verdict: NOT APPLICABLE

No high-risk runtime paths are changed. This PR changes CI/process/docs only.

## Acceptance Proof

Commands:

```bash
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected result:

```text
AGENT REVIEW EVIDENCE GATE: PASSED
```

## Runtime Proof Required After Merge

Command:

```bash
gh pr checks <next-pr-number> --watch
```

Expected evidence:

```text
Agent Review Evidence Gate passes only when docs/agent_reviews/*.md exists and contains all required sections.
```

## What This PR Does Not Prove

1. It does not prove the bot runtime is stable.
2. It does not prove feed, WebSocket, strategy, execution, or broker behavior.
3. It does not backfill historical PR evidence automatically.
4. It does not judge the quality of the agent analysis beyond required structure and high-risk declaration.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21
