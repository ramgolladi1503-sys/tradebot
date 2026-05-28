# AGENT-ELITE-12 — Daedalus Anti-PR-Loop Detector

mode: REVIEW
candidate_id: AGENT-ELITE-12-DAEDALUS-ANTI-PR-LOOP-DETECTOR
decision: review_pending
reason: daedalus_static_pr_loop_detection
source: docs/agent_reviews/AGENT_ELITE_12_DAEDALUS_ANTI_LOOP.md
timestamp: 2026-05-28T19:40:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #384
Parent: #372
Depends on: #383 / PR #399 / merge commit b8d563afaeb180e13d62477c4d396f184d1e3b6f

## Agent Work Contract

This PR implements AGENT-ELITE-12 only.

The work adds a static Daedalus detector that reports PR-loop risk when a PR claims engineering progress without reducing current blockers or proving the scoped outcome.

It must not mutate GitHub, create issues, close pull requests, auto-comment, run product runtime code, call brokers, modify broker code, change strategy/ranking formulas, or change dashboard/UI behavior.

## Scope Guard

Allowed:

- Add `tools/code_excellence/daedalus/pr_loop_detector.py`.
- Export the detector from `tools/code_excellence/daedalus/__init__.py`.
- Add focused tests in `tests/test_daedalus_pr_loop_detector.py`.
- Add this agent-review evidence file.

Not allowed:

- GitHub mutation.
- Issue creation.
- Pull request closing.
- Auto-commenting.
- Runtime execution.
- Broker calls.
- Broker code changes.
- Strategy/ranking formula changes.
- Dashboard/UI changes.
- External agent calls.
- Test skip/xfail.

## High-Risk Path Review

This PR adds isolated static code-excellence tooling only.

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

Question: Does this block or close pull requests?

Answer: No. It returns a local report only.

Question: Does this decide whether GitHub work is merged?

Answer: No. It only classifies loop risk using supplied static inputs.

Question: What happens when code changes have no tests?

Answer: The report blocks with `code_change_without_tests`.

Question: What happens when the work claims a blocker fix but does not reduce the current blocker count?

Answer: The report blocks with `blocker_not_reduced` unless current scope reduction is explicitly supplied.

Question: Can documentation-only work pass?

Answer: Yes, when it is explicitly documentation-scoped and has done-means plus acceptance proof.

## Hermes Review

The implementation is intentionally additive:

- Adds `PRLoopInput`.
- Adds `PRLoopReport`.
- Adds `detect_pr_loop_risk(...)`.
- Flags code changes without tests.
- Flags claimed blocker fixes without blocker reduction.
- Flags absent done-means.
- Flags absent acceptance proof.
- Flags vague next steps and broad follow-up chains.
- Allows explicit valid documentation-only work.

## GSD Review

Smallest safe implementation:

- Keep anti-loop logic isolated under `tools/code_excellence/daedalus/`.
- No integration into CI gates yet.
- No repository mutation behavior.
- No runtime behavior.
- Deterministic pure report tests only.

Files changed:

- `tools/code_excellence/daedalus/__init__.py`
- `tools/code_excellence/daedalus/pr_loop_detector.py`
- `tests/test_daedalus_pr_loop_detector.py`
- `docs/agent_reviews/AGENT_ELITE_12_DAEDALUS_ANTI_LOOP.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_daedalus_pr_loop_detector.py -q
```

Safety assertions:

- No GitHub mutation path exists.
- No issue creation path exists.
- No pull request closing path exists.
- No auto-comment path exists.
- No runtime import of target Tradebot modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard behavior change.
- Broker code is untouched.
- Strategy/ranking formulas are untouched.

## Acceptance Proof

The tests prove:

- Claimed blocker fix without proof/test coverage is blocked as PR-loop risk.
- Explicit documentation-only PR can pass.
- Follow-up work without current scope reduction warns or blocks.
- Work with done-means and proof passes.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is static code-excellence analysis only.

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
