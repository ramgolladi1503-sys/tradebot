# Verify TradeBot Research Gates

Validate a TradeBot research milestone without trusting narrative completion claims.

1. Call `tradebot-evidence.list_research_contexts` and select the explicit context.
2. Read the contract, safety boundaries, cycle status, consumed-evidence registry, candidate fingerprint, and agent attempts.
3. Call `tradebot-git-audit.get_worktree_status` and `verify_commit_scope` for the claimed implementation branch.
4. Verify all referenced artifact SHA-256 values.
5. Run the applicable machine gates in order: bootstrap, Wave 1, temporal, candidate freeze, WFA, determinism, oracle, and publication.
6. Stop at the first `FAIL`; list the exact failed checks and assign one repair action.
7. Do not edit status files to match the desired result.
8. Report `PASS` only when the corresponding MCP gate returns `PASS`.
