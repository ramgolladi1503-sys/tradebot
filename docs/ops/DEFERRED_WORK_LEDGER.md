# Deferred Work Ledger

## Purpose

This ledger captures work that is real, important, and intentionally deferred.

It is not a dumping ground for vague ideas. If an item cannot explain context, reason for deferral, trigger to revisit, and acceptance proof, it does not belong here.

## Rules

1. Every deferred item must have a stable ID.
2. Every item must explain why it is not being done now.
3. Every item must define the trigger that makes it relevant again.
4. Every item must define acceptance proof.
5. Open items must be reviewed before starting related PRs.
6. Completed items must keep proof, not just a status flip.
7. This file stays manual until the ledger proves enough value to justify a CLI.

## Status Values

- Open
- In Progress
- Blocked
- Closed
- Rejected

## Priority Values

- P0: Must handle before next related runtime or safety work.
- P1: Should handle in the next related PR or architecture cleanup.
- P2: Useful cleanup; not blocking current work.
- P3: Nice-to-have; only do if already touching the area.

## Item Template

```text
ID: TODO-YYYY-MM-DD-###
Title:
Status:
Priority:
Area:
Added during:
Context:
Why deferred:
Trigger to revisit:
Acceptance proof:
Linked PRs/files/commands:
Owner:
Closed proof:
```

---

## Open Items

### TODO-2026-05-22-001 — Fix completed-flow killed_hypotheses wording

ID: TODO-2026-05-22-001
Status: Open
Priority: P2
Area: debug_forensics
Added during: Post-PR #187 runtime proof
Context: Debug forensics completed the startup flow and reported `FLOW_CONTRACT_COMPLETE` with `last_confirmed_event=ORCHESTRATOR_CYCLE_COMPLETED`, but the `killed_hypotheses` text still included stale wording implying startup was inside orchestrator construction.
Why deferred: It does not block runtime startup, cycle completion, or root-cause debugging. It is report-quality cleanup.
Trigger to revisit: EDGE-30 debug-forensics architecture ADR or the next debug-forensics report-format cleanup.
Acceptance proof: Completed-flow reports produce completed-flow wording and no longer imply constructor-stage blockage after `ORCHESTRATOR_CYCLE_COMPLETED`.
Linked PRs/files/commands: `core/debug_forensics/flow_analyzer.py`; `python scripts/debug_forensics.py --profile startup`
Owner: Ram / next implementation agent
Closed proof:

### TODO-2026-05-22-002 — Write Debug Forensics Architecture ADR

ID: TODO-2026-05-22-002
Status: Open
Priority: P1
Area: architecture/debug_forensics
Added during: EDGE-26 through EDGE-29 startup-debugging sequence
Context: Debug forensics evolved from startup evidence reader into a proven runtime diagnosis architecture. It found the actual root issue where the fast loop called heavy feed diagnostics before honoring a due timer cycle. The rationale, boundaries, and anti-patterns need to be recorded.
Why deferred: Runtime blocker was prioritized first and fixed in PR #187. ADR should follow after proof is complete.
Trigger to revisit: Next documentation/architecture PR after PR #187.
Acceptance proof: ADR documents the problem, proof chain, root cause, fix, enforcement model, and explicit rule that this architecture must not become endless probe PRs.
Linked PRs/files/commands: PR #180, PR #183, PR #184, PR #185, PR #186, PR #187; `docs/agent_reviews/`; `core/debug_forensics/`
Owner: Ram / next implementation agent
Closed proof:

### TODO-2026-05-22-003 — Review whether Deferred Work Ledger deserves a CLI

ID: TODO-2026-05-22-003
Status: Open
Priority: P3
Area: ops/deferred_work
Added during: EDGE-30 Deferred Work Ledger creation
Context: A manual markdown ledger is enough now. A CLI may become useful later for add/list/close operations, but adding it immediately would be overengineering.
Why deferred: The ledger must prove usage first. Tooling before workflow adoption creates maintenance noise.
Trigger to revisit: After at least 10 real deferred items are added and at least 3 are closed with proof.
Acceptance proof: If justified, add a tiny deterministic `scripts/deferred_work.py` with add/list/close validation and tests. If not justified, keep this item open or reject it.
Linked PRs/files/commands: `docs/ops/DEFERRED_WORK_LEDGER.md`
Owner: Ram / next implementation agent
Closed proof:

---

## Closed Items

No closed items yet.
