# Final Summary

Maintenance verdict: `CLEANUP_INSUFFICIENT_FOR_OUTCOME_RUN`

Outcome verdict: `ORB_OUTCOMES_INCOMPLETE`

What happened:

- Collected filesystem, process, deleted-open-file, cache, artifact, PR, and worktree diagnostics.
- Verified PR #674 remains open at head `2219b0a6aa7294e2ff4124a80b5c7b182bd220ca`.
- Verified the PR #674 worktree `/Users/madhuram/tradebot-strategy-outcomes-foundation` is clean.
- Did not run ORB outcome measurement because free space is about `3.60 GiB`, below the required `20 GiB` pre-run gate.
- Did not delete any files because safe automatic reclaim was insufficient and higher-yield candidates require manual approval or are protected.

Safety statements:

- PRODUCTION FILES TOUCHED: NONE
- AUTHORITATIVE DATA FILES DELETED: NONE
- OPEN PR WORKTREES DELETED: NONE
- UNIQUE COMMITS LOST: NONE
- UNCOMMITTED FILES LOST: NONE

Manual-review reclaim candidates:

- macOS deleted-open wallpaper file: about `445 MiB`.
- `/Users/madhuram/tradebot/.venv`: about `2.58 GiB`; virtualenv, not auto-deleted.
- `/Users/madhuram/tradebot/.mypy_cache`: about `111 MiB`; protected shared checkout cache, not deleted.
- `/Users/madhuram/tradebot/ui/node_modules`: about `65 MiB`; dependency directory, not auto-deleted.
- Old/detached worktrees: require explicit full worktree-removal audit and approval before removal.

PR #674 action:

- No update was pushed to PR #674.
- The outcome run remains incomplete by gate, not by replay failure.
