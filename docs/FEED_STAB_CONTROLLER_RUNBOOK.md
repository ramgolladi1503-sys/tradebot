# FEED-STAB Controller Runbook

The FEED-STAB controller keeps PR lifecycle work durable when Codex or an interactive terminal stops.

Script:

`./scripts/dev/feed_stab_sequence_controller.sh`

It polls a PR every 120 seconds by default, waits through pending checks, stops on red checks with inspection commands, merges when checks are green, syncs `main`, and then stops with:

`READY_FOR_NEXT_PR_IMPLEMENTATION: FEED-STAB-XX`

## Run with tmux

```bash
cd /Users/madhuram/tradebot
tmux new -s feedstab
POLL_SECONDS=120 scripts/dev/feed_stab_sequence_controller.sh 534 2
```

## Run with nohup

```bash
cd /Users/madhuram/tradebot
nohup env POLL_SECONDS=120 scripts/dev/feed_stab_sequence_controller.sh 534 2 > /tmp/feedstab-controller.log 2>&1 &
tail -f /tmp/feedstab-controller.log
```

## Resume after stop marker

If the controller stops with `READY_FOR_NEXT_PR_IMPLEMENTATION: FEED-STAB-XX`, implement the next PR from fresh synced `origin/main`, then rerun the controller with the updated PR number and sequence number.

## Rules

- Implement the next PR only from synced `origin/main`.
- Never start the next PR before the current PR is green, merged, and local `main` is synced.
- If checks go red, inspect the failed run, fix the current branch, push, then rerun the controller.
