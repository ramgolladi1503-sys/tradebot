# Path Inventory

- /Users/madhuram/tradebot | KEEP_CANONICAL | Canonical repository is protected and dirty. | action: No action.
- /Users/madhuram/.codex/worktrees | SAFE_DELETE_GENERATED_ARTIFACT | 37 clean detached registered TradeBot worktrees passed all automatic removal gates. | action: Completed removal with git worktree remove.
- /Users/madhuram/.codex/worktrees/b411/tradebot | MANUAL_REVIEW | Exists under .codex/worktrees but is not part of the registered TradeBot worktree set. | action: Do not auto-delete.
- /Users/madhuram/.codex/worktrees/b411/algotradify | MANUAL_REVIEW | Outside TradeBot scope and not a registered TradeBot worktree. | action: Leave untouched unless scope widens.
- /private/tmp/tradebot-four-strategy-baseline | MANUAL_REVIEW | Registered tmp worktree has unique commits and non-empty status. | action: Do not auto-delete.
- /private/tmp/orb_owner_audit | MANUAL_REVIEW | Registered tmp worktree has branch and unique commits. | action: Do not auto-delete.
- /private/tmp/tradebot-main-review | MANUAL_REVIEW | Broken registered metadata was pruned, but the directory still exists on disk. | action: Inspect manually before any deletion.
- /Users/madhuram/tradebot-strategy-outcomes-foundation | KEEP_OPEN_PR | Associated with open PR #674. | action: No action.
- /Users/madhuram/tradebot-trend-provenance-boundary | KEEP_OPEN_PR | Associated with open PR #673. | action: No action.
- /Users/madhuram/.codex/worktrees/tradebot/orb-context-cycle-cutoff | KEEP_OPEN_PR | Associated with open PR #659. | action: No action.
- /private/tmp/orb-postmerge-final-140025d8-smoke-1784401556 | KEEP_OPEN_PR | Known exact-main ORB evidence root protected while PR #672 remains open or uncertain. | action: No action.
- /private/tmp/orb-postmerge-final-140025d8-12shard-1784401606 | KEEP_OPEN_PR | Known exact-main ORB evidence root protected while PR #672 remains open or uncertain. | action: No action.