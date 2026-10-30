# Pre-GitHub Agent Team Runtime — Pilot

This pilot adds an actual process launcher to the existing TradeBot delivery
organization. It does **not** replace the permanent delivery orchestrator under
.agents/workflows, the offline core.delivery transition engine, or the human
GitHub release gate.

## What is implemented

- Uses eight separate Codex CLI exec processes, not role labels in a single
  model response.
- Dispatch order: BA/PO, Grill Me/Hermes, GSD, QA/Technical & Quant Analyst,
  then Senior QA. Launches sequentially; never exceeds the 3-child limit.
- Requires an existing JSON work item with bytes identical to committed HEAD.
- Uses Codex's documented read-only sandbox and structured-output schema.
- Records a per-invocation ID and a SHA-256 digest of the process output.
- Stops on role BLOCK, invalid output, unavailable Codex, or timeout.
- Records the outcome in a local JSON ledger, **not** as QA/UAT/product
  acceptance evidence, and never pushes, merges, or places orders.

## Run from the TradeBot repository root

Requires an authenticated and installed Codex CLI. Calls can consume model
usage. The work item must be committed.

~~~bash
python -m tools.pre_github_team \
  --work-item governance/evidence/work_items/EVS-001.json \
  --out .runtime/pre_github/evs001-team.json
~~~

Exit 0 means only that eight separate *read-only review responses* were
collected. It does **not** mean QA_PASSED, PRODUCT_ACCEPTED, or
RELEASE_READY. Exit 2 means UNSATISFIED and blocks dependent work.

For an Antigravity-led task, a human or approved automation may invoke the same
Python CLI from the repository terminal. This pilot does **not** claim the
Antigravity IDE automatically invokes it or that Hermes Agent, Paperclip,
Mnemosyne, or SkillClaw have been installed.

## Verified tests

~~~bash
python -m unittest discover -s tests -p test_pre_github_team.py -v
~~~

Tests use fake process responses, plus a real temporary Git repository to
exercise committed-work-item matching. They do not start paid Codex sessions.

## Important boundaries / next steps

1. Each Codex process is real when the CLI is installed, but eight model
   processes are **not** proof of independent cognition or verified identity.
2. Evidence references are unverified strings; a machine-verifiable evidence
   resolver and authenticated reviewer identity remain necessary.
3. This pilot is read-only. GSD proposes a patch plan but does not implement.
   The existing scoped development/QA/UAT lifecycle must still run.
4. No IDE-wide interception or Control Tower synchronization is implemented.
   Future adapters should attach to the existing TradeBot delivery engine and
   the existing Aixion Control Tower signed-capability approval bridge.
5. Specialized repos (Paperclip, Mnemosyne, Hermes, SkillClaw, evolution tools)
   require separate compatibility/security testing; do not install them just to
   meet a checklist.
6. No release ruleset or broker/runtime code is changed by this pilot.
