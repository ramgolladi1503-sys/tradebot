---
name: verify-research-handoff
description: Independently verifies a TradeBot research subagent handoff, commit scope, artifact hashes, tests, evidence locks, and gate status before integration.
---

# Verify a TradeBot Research Handoff

Use this skill whenever an agent claims that a research, audit, data, WFA, oracle, or publication task is complete.

## Procedure

1. Query `tradebot-evidence.list_agent_attempts` and locate the exact attempt ID.
2. Read the exact handoff with `tradebot-evidence.get_agent_handoff`.
3. Query `tradebot-git-audit.get_worktree_status` and confirm the worktree, branch, starting SHA, ending SHA, and cleanliness.
4. Run `tradebot-git-audit.verify_commit_scope` using the assignment's owned and prohibited paths.
5. Verify every artifact with `tradebot-evidence.verify_artifact_hash`.
6. Confirm holdout and fresh-confirmation status with `tradebot-evidence.get_holdout_status`.
7. Run the matching `tradebot-gates` tool.
8. Reject any handoff whose gate is not `PASS`, whose hashes do not match, whose scope is violated, or whose evidence cannot be independently recomputed.

## Required output

Return only:

- attempt ID;
- branch and SHAs;
- scope verdict;
- artifact-hash verdict;
- holdout status;
- machine gate verdict;
- accepted, rejected, or repair required;
- one exact next action.

Never accept a polished summary as evidence.
