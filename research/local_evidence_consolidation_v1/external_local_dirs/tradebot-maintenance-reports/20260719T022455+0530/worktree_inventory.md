# Worktree Inventory

Source: `git worktree list --porcelain`

- Worktrees observed: `32`
- PR #674 worktree: `/Users/madhuram/tradebot-strategy-outcomes-foundation`
- PR #674 head: `2219b0a6aa7294e2ff4124a80b5c7b182bd220ca`
- PR #674 cleanliness: clean
- Worktrees removed: `0`

Decision:

- Preserve all worktrees in this task.
- Do not remove `/private/tmp/orb_owner_audit`; it is a registered git worktree.
- Do not remove detached worktrees without the full uniqueness/uncommitted/open-PR/user-approval gate.
