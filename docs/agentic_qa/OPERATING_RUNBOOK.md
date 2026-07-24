# Operating Runbook

1. Create a fresh isolated worktree or CI checkout from the intended source commit.
2. Produce a frozen evidence bundle from the existing strict backtest/WFA pipeline.
3. Hash every artifact and write the hashes into the manifest.
4. Run the 70-control auditor.
5. Treat `REJECTED`, `INSUFFICIENT_EVIDENCE`, and `AUDITOR_ERROR` as hard stops.
6. Review advisory agent output only after deterministic completion.
7. Require a named human approver before paper or controlled-deployment promotion.
8. Archive the manifest, report, evaluation output, source commit, and approval record.

Never rerun a failed experiment by silently changing data, parameters, costs, or policy. Create a new run ID and evidence bundle.
