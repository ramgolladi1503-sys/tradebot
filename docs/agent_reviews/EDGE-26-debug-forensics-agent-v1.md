# EDGE-26 — Debug Forensics Agent v1

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-26-debug-forensics-agent-v1
- decision: ADD_STARTUP_DEBUG_FORENSICS_AGENT_V1
- reason: Existing lifecycle probes produce evidence, but the repo needs a deterministic reader that compares expected startup flow against actual runtime proof and reports the earliest unproven boundary.
- timestamp: 2026-05-21T17:55:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-26-debug-forensics-agent-v1.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: EDGE-26 / PR #180
- Branch: edge26-debug-forensics-agent-v1
- Scope: add read-only startup debug forensics v1.
- Allowed files:
  - core/debug_forensics/__init__.py
  - core/debug_forensics/models.py
  - core/debug_forensics/flow_contracts.py
  - core/debug_forensics/evidence_reader.py
  - core/debug_forensics/flow_analyzer.py
  - core/debug_forensics/report_writer.py
  - scripts/debug_forensics.py
  - tests/test_debug_forensics_startup.py
  - docs/agent_reviews/EDGE-26-debug-forensics-agent-v1.md
- Forbidden behaviors:
  - No existing runtime-path changes.
  - No strategy-path changes.
  - No UI changes.
  - No autonomous edits.
  - No external agent calls.
  - No automatic PR creation.
- Default enforcement:
  - CLI defaults to the startup profile.
  - Evidence must pass schema and run identity checks.
  - Startup profile remains read-only.
  - Unsafe evidence creates a safety finding.
  - Missing proof creates a blocker finding.
  - Blocker, safety, and insufficient-evidence findings return non-zero exit code.
  - Reports are written by default unless explicitly disabled.

## Scope Guard

Verdict: PASS

Checked:

- New code is isolated under core/debug_forensics/ and scripts/debug_forensics.py.
- Existing runtime writers are not changed.
- Existing probes are not changed.
- Existing strategy, feed, dashboard, and risk paths are not changed.
- The new tool reads existing evidence only.
- The new tool does not perform network calls.
- The new tool does not mutate runtime state except writing diagnostic report files.

Blocking issues: none.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk area touched:

- None of the existing high-risk runtime modules are changed.

Architecture risk:

- A forensics tool can create fake confidence if it accepts stale, mixed, or malformed evidence.

Mitigation:

- Event schema is validated.
- run_id is required.
- boot_epoch consistency is enforced.
- timestamp monotonicity is enforced.
- unsafe startup-profile evidence is flagged.
- forbidden startup events are flagged.

## Grill Me Review

Verdict: PASS_WITH_LIMITATIONS

Weak assumptions challenged:

1. Assumption: Latest evidence is reliable.
   - Countermeasure: jsonl is read directly and latest mismatch is treated as a warning.
2. Assumption: Events belong to one run.
   - Countermeasure: selected run_id and boot_epoch consistency are enforced.
3. Assumption: Missing event means root cause is known.
   - Countermeasure: report says first missing proof boundary, not root cause certainty.
4. Assumption: This can be an agent that fixes code.
   - Countermeasure: implementation is read-only and diagnostic only.

Failure modes still possible:

1. If probes are not installed, forensics can only report missing evidence.
2. If runtime never writes lifecycle rows, forensics returns insufficient evidence.
3. If expected flow evolves, the flow contract must be updated in a later profile/contract PR.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Models are typed dataclasses.
2. Flow contracts are centralized.
3. Evidence loading is separated from analysis.
4. Analysis is separated from report writing.
5. CLI is thin and uses the core modules.
6. Reports are machine-readable JSON and human-readable Markdown.

Why this should not need a rewrite:

1. New profiles can be added through flow contracts instead of changing the core reader.
2. Evidence validation is generic for lifecycle events.
3. Report schema is versioned.
4. Severity model is explicit.
5. CLI already supports profile, run_id, logs-dir, and reports-dir overrides.

## GSD Review

Verdict: PASS

Execution plan:

1. Add debug forensics data models.
2. Add startup flow contract.
3. Add lifecycle evidence reader.
4. Add startup flow analyzer.
5. Add report writer.
6. Add CLI.
7. Add focused scenario tests.
8. Add agent review evidence.

4-PR architecture rollout:

1. EDGE-26 — Startup Debug Forensics v1.
2. EDGE-27 — Hypothesis Killer and Diagnostic Scope Enrichment.
3. EDGE-28 — Additional Profiles and Contract Registry Hardening.
4. EDGE-29 — Architecture Decision Record and Default Enforcement Documentation.

The final EDGE-29 doc must explain why this architecture exists, what PR loops it prevents, what evidence it requires, and what it must never become.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_debug_forensics_startup.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected behavior:

1. First missing startup event produces BLOCKER.
2. Unsafe startup-profile evidence produces SAFETY_VIOLATION.
3. Mixed boot epochs produce INSUFFICIENT_EVIDENCE.
4. Non-monotonic timestamps invalidate evidence.
5. JSON and Markdown reports are written.

## Acceptance Proof

Required commands:

```bash
python -m pytest tests/test_debug_forensics_startup.py -q
python scripts/debug_forensics.py --profile startup --no-write-report
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected results:

- Focused tests pass.
- CLI prints JSON report.
- CLI returns non-zero when current evidence has a blocker, safety issue, or insufficient evidence.
- Agent Review Evidence Gate passes.

## Runtime Proof Required After Merge

After merge, run:

```bash
python scripts/debug_forensics.py --profile startup
```

Expected artifacts:

```text
.runtime/reports/debug_forensics/startup_latest.json
.runtime/reports/debug_forensics/startup_<run_id>.md
```

Expected report fields:

```text
last_confirmed_event
first_missing_event
findings
killed_hypotheses
next_diagnostic_scope
forbidden_distractions
is_order_action=false
```

## What This PR Does Not Prove

1. It does not prove strategy quality.
2. It does not prove profitability.
3. It does not fix startup hangs.
4. It does not add new probes.
5. It does not replace human review.
6. It does not perform automatic code edits.
7. It does not make external agent calls.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21
