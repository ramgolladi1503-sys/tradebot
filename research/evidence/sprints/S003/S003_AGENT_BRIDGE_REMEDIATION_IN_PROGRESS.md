# MROS S003 — Isolated Agent Bridge Remediation In Progress

Date: 2026-08-08
Program boundary: `M1 → WP001 → S003`
Status: BLOCKED_PENDING_MAC_SMOKE
Authority: Research / R
Runtime authority: NONE
M9: NOT_STARTED

## Purpose

Record the concrete remediation for the remaining S003 bootstrap blocker without falsely claiming that the execution backend is already operational.

## Implemented remediation

A dedicated implementation branch now exists:

`research/mros-agent-bridge-v1`

It contains:

- `scripts/mros/mros_agent_bridge.py` — allowlisted exact-SHA job execution core;
- `scripts/mros/mros_agent_bridge_server.py` — optional authenticated localhost facade;
- `scripts/mros/mros_agent_git_worker.py` — Git mailbox pull worker;
- `scripts/mros/mros_codex_backend.py` — fresh ephemeral read-only Codex backend adapter;
- `scripts/mros/bootstrap_mros_agent_bridge_mac.sh` — Mac bootstrap/preflight;
- `tests/mros/test_mros_agent_bridge.py` — fail-closed/isolation tests;
- `research/governance/review_board/MROS_AGENT_BRIDGE_CONFIG.example.json` — bounded configuration example.

Transport is isolated from program authority on:

`automation/mros-agent-queue-v1`

The queue branch is a mailbox only. It MUST NOT accept sprints, update MROS authority, grant runtime authority, or replace the program branch.

## Security / scope properties

The bridge design explicitly provides:

- no arbitrary-shell HTTP endpoint;
- exact 40-hex candidate SHA binding;
- allowlisted backend names and argv templates;
- reviewer/auditor role-type validation;
- repository path traversal rejection;
- output-path collision rejection;
- fresh detached Git worktree per model job;
- fresh process environment;
- Codex `exec --ephemeral` invocation;
- Codex read-only sandbox for reviewer/auditor jobs;
- immutable local JSONL job events;
- unique queue request/result/receipt paths;
- queue result commits separated from `research/mros-program-v1`;
- runtime authority hard-coded to `NONE` in bridge evidence;
- broker actions explicitly not allowed.

The Git worker fetches both the mailbox branch and `research/mros-program-v1` so newly frozen candidate SHAs can be resolved without merging program-state commits into the mailbox.

## Non-certifying smoke already queued

Queue packet:

`research/evidence/sprints/S003/agent_queue/packets/SMOKE_R99.md`

Queue request:

`research/evidence/sprints/S003/agent_queue/requests/SMOKE_R99.json`

Queue request commit:

`3ef9ae186c08792b52123481f1f164e348602fa1`

The smoke is intentionally role `R99` and MUST NOT be counted toward S003 reviewer quorum or Board calibration/certification. It exists only to prove that GitHub -> Mac worker -> fresh Codex -> isolated exact-SHA worktree -> GitHub result is operational.

## Remaining legal gate

The bridge is NOT yet proven operational because this ChatGPT execution sandbox cannot start a process on the operator's Mac.

Required next evidence:

1. run Mac bootstrap/preflight;
2. bridge tests pass natively;
3. local Codex installation/auth/network health is usable;
4. start the Git mailbox worker;
5. queued `SMOKE_R99` produces a non-empty result and receipt on `automation/mros-agent-queue-v1`;
6. result proves exact candidate `fd16f526842b9f4f27d7fd06859b059812e10796`, repository read PASS, runtime authority NONE, broker actions NONE;
7. independently inspect commit scope and worker receipt.

Only after those checks may the previous `CALLABLE_ISOLATED_REVIEWER_BACKEND = NOT_FOUND` blocker be superseded.

## Boundary preservation

- S003 remains BLOCKED pending Mac smoke evidence.
- Review Board remains IMPLEMENTED_NOT_CALIBRATED.
- Audit Board remains IMPLEMENTED_NOT_CALIBRATED.
- Autonomous authority remains NOT_AUTHORIZED.
- M2 remains NOT_STARTED.
- M9 remains NOT_STARTED.
- Runtime authority remains NONE.
