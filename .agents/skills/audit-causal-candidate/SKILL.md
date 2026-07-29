---
name: audit-causal-candidate
description: Audits a frozen TradeBot strategy candidate for causal data use, next-bar execution, session isolation, controls, determinism, and holdout safety.
---

# Audit a Causal Strategy Candidate

Use only after a deterministic base candidate and fingerprint exist.

## Procedure

1. Read the frozen contract and candidate fingerprint with `tradebot-evidence`.
2. Verify the consumed-evidence registry and confirm holdout remains locked.
3. Use `tradebot-data-audit` to verify schema, timestamp order, duplicates, session counts, missing intervals, and backward-only joins.
4. Verify that all features stop at the decision timestamp and entry occurs on the next executable bar.
5. Require negative controls, latency stress, concentration checks, multiple-testing adjustment, two-run determinism, and an independent oracle.
6. Evaluate the temporal, candidate-freeze, WFA, determinism, and oracle gates.
7. Do not evaluate option profitability until the underlying candidate passes fresh out-of-sample confirmation.

## Fail-closed rules

- Any missing artifact, stale hash, future match, same-bar entry, cross-session outcome, consumed holdout, or failing gate closes the candidate.
- A positive P&L or profit factor alone is not structural-edge evidence.
- Do not change thresholds after reading validation or holdout outcomes.
