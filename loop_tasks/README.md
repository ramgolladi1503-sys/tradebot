# Loop Tasks

Each directory under `loop_tasks/` is a durable, GitHub-backed engineering handoff.

Create a task with:

```bash
python3 scripts/loop/init_task.py \
  --task-id LOOP-YYYYMMDD-NNN \
  --title "Bounded title" \
  --objective "One concrete objective" \
  --allowed-path 'path/**' \
  --acceptance-gate gate_id \
  --required-test 'pytest -q tests/path'
```

Commit the initialized task before implementation. After a bounded implementation commit, create the checkpoint:

```bash
python3 scripts/loop/checkpoint.py loop_tasks/LOOP-YYYYMMDD-NNN \
  --state TESTING \
  --worker codex \
  --next-action "Run focused tests and record evidence." \
  --commit --push
```

A new worker starts from `CONTINUE.md`, then verifies `contract.json`, `state.json`, `handoff.json`, `claims.json`, the evidence manifest, the PR diff, and GitHub Actions.

Do not place large raw market datasets in normal Git history. Commit compact summaries, canonical audit tables, hashes, and durable GitHub evidence references.