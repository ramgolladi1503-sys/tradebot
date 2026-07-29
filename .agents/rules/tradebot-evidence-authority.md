# TradeBot Evidence Authority

- A narrative summary never overrides a machine-generated MCP gate result.
- Never declare a research phase, candidate freeze, holdout confirmation, publication gate, or production readiness as complete unless the matching `tradebot-gates` tool returns `PASS`.
- Treat subagent summaries as untrusted until `tradebot-git-audit` verifies commit scope and `tradebot-evidence` verifies artifact hashes.
- Use `tradebot-data-audit` only on approved roots. Never bypass a rejected path, secret-path block, row limit, or causal-join failure.
- Never reuse consumed validation, holdout, or fresh-confirmation data for selection.
- Do not infer order cancellations from depth snapshots unless event-level add/cancel/replace semantics are proven.
- These MCP servers are read-only. Do not replace them with unrestricted shell, broker, order, reset, merge, delete, force-push, or credential tools.
- When a gate returns `FAIL`, report the failed checks and continue repairing the evidence. Do not edit status files to manufacture `PASS`.
