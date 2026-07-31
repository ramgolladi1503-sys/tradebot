Read root `AGENTS.md` first.

Continue `<TASK_ID>` from `loop_tasks/<TASK_ID>/`.

1. Read `CONTINUE.md`, `contract.json`, `state.json`, `handoff.json`, `claims.json`, and `evidence/manifest.json`.
2. Verify the current branch and remote head before editing.
3. Perform only `state.next_action` inside `contract.allowed_paths`.
4. Do not expand frozen acceptance criteria; record optional improvements as backlog.
5. Run focused required tests, not broad repeated audits.
6. Commit implementation changes.
7. Generate a second interrupt-safe checkpoint commit and push it before stopping.
8. Do not merge, deploy, start live trading, use broker credentials, or perform order actions.

Return only:

```text
Task:
State:
Code SHA:
Checkpoint SHA:
Tests:
Blockers:
Next action:
GitHub paths:
```
