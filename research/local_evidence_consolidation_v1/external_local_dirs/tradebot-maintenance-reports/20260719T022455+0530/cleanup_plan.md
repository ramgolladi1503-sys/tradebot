# Cleanup Plan

Approved automatic deletions:

- None.

Reasons:

- The shared checkout `/Users/madhuram/tradebot` is protected/read-only in this task.
- Virtual environments are not automatic deletion candidates.
- `node_modules` is not an allowed automatic cache deletion class in the user scope.
- Registered worktrees must not be removed without the full worktree-removal gate.
- Replay artifacts are small, potentially evidence-bearing, or registered worktrees.

Manual-review candidates:

- macOS deleted-open wallpaper file, about `445 MiB`: reclaim only by closing/restarting the owning system process/session, not by TradeBot cleanup.
- `/Users/madhuram/tradebot/.venv`, about `2.58 GiB`: manual dependency rebuild decision required.
- `/Users/madhuram/tradebot/.mypy_cache`, about `111 MiB`: protected shared checkout cache; deletion was not performed.
- `/Users/madhuram/tradebot/ui/node_modules`, about `65 MiB`: dependency directory; deletion was not performed.
- Detached/stale-looking worktrees: require explicit worktree-removal audit and approval.

Outcome decision:

- Do not start ORB outcome measurement. Current free space is about `3.39 GiB`, below the `20 GiB` pre-run gate.
