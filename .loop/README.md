# GitHub-First Loop Engineering

This directory defines the durable handoff protocol for agent-assisted engineering in TradeBot.

GitHub is the source of truth. Local uncommitted work is non-authoritative and cannot satisfy a frozen acceptance gate.

Each bounded task lives under `loop_tasks/<TASK_ID>/` and contains:

- `contract.json` — frozen objective, scope, gates, budgets, and human approvals.
- `state.json` — current lifecycle state and next action.
- `handoff.json` — exact code SHA, changed paths, commands, tests, blockers, and takeover instructions.
- `claims.json` — explicit claims linked to proof IDs.
- `evidence/manifest.json` — hashes and provenance for evidence.
- `CONTINUE.md` — compact context for Codex, ChatGPT, Antigravity, or a human.

## Two-commit checkpoint protocol

1. Commit implementation changes.
2. Record that commit as `code_sha`.
3. Generate task checkpoint files referencing `code_sha`.
4. Commit checkpoint metadata separately.
5. Push the branch.
6. Let GitHub Actions independently validate scope, ancestry, claims, evidence, and lifecycle state.

Workers do not self-certify completion. The task state advances only when frozen gates have evidence and the loop validator accepts the transition.

This framework never merges, deploys, starts live trading, calls brokers, or changes runtime safety controls.