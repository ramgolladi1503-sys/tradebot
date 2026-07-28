# Cleanup Summary

- Task date anchor: 2026-07-18
- Removed 37 registered safe `.codex` TradeBot worktrees with `git worktree remove`.
- Reclaimed approximately 756.1 MiB from those worktrees.
- Data-volume free space increased from about 1.9 GiB to 2.8 GiB.
- `.codex/worktrees` dropped from about 2.6 GiB to 1.8 GiB.
- `.codex` overall dropped from about 4.2 GiB to 3.5 GiB.
- No TradeBot runtime process was terminated.
- Canonical TradeBot repository remained dirty but unchanged by this cleanup.
- Remaining pressure is mostly canonical runtime data/logs plus manual-review tmp/orphan worktrees.