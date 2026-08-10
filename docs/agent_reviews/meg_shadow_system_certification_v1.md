# Agent Review — MEG Shadow System Certification V1

## Agent Work Contract

- source_agent: ChatGPT
- action: `REBUILD_WHOLE_SYSTEM_CERTIFICATION_FOR_MEG_SHADOW`
- base: PR #772 reliability completion branch
- source material: curated PR #761 QA/auth/test-integrity work and PR #762 certification intent
- scope: offline same-SHA contract certification plus final assembly with the real PR #763 post-market reliability certificate
- forbidden: strategy-profitability certification, multi-strategy coverage, broker writes, order actions, live-loop changes, and feed/MEG runtime mutation

## Scope Guard

The PR is limited to QA plans/risk documentation, test-integrity tooling, a minimal fail-closed authentication correction, auth behavior tests, a MEG-shadow certification package, its CLI/tests, and a dedicated read-only workflow. It does not modify feed, WebSocket, Market Event Graph, persistence, scoring, strategy, risk, approval, broker, or order-routing logic.

## Grill Me Review

- Can tests alone produce a final green certificate? No. Offline gates may pass, but final certification also requires a real `PASS_READ_ONLY_POST_MARKET_RELIABILITY` certificate from PR #772 using a fresh PR #763 session.
- Does this certify all historical strategies? No. The scope is the one authoritative advisory-only MEG shadow path.
- Does an unknown network/auth state count as usable authentication? No. `UNKNOWN_NETWORK` is fail-closed with `ok=false`.
- Can the certificate grant paper or live execution? No. The certificate explicitly preserves `order_authority=false`, `broker_write_authority=false`, and `allowed_for_live_execution=false`.
- Can missing test files or skipped gate groups be treated as success? No. Every required gate group must exist, execute, and return zero on one immutable SHA.

## Hermes Review

The evidence chain is:

```text
same-SHA offline gate report
  auth/startup
  feed/subscription contracts
  persistence/shutdown
  MEG observation contracts
  authority/UI
  manual approval + broker firewall
  restart/reconciliation
  AI reliability + evidence integrity
+ real PR #763 post-market reliability certificate
→ final MEG shadow system certificate
```

Each report includes commands, return codes, durations, output tails, repository SHA, and a semantic hash. The final assembler checks both certificates instead of trusting a prose summary.

## GSD Review

PR #761 is not merged wholesale. Its work is reduced into three bounded groups:

1. QA plan and module-risk documentation;
2. test-integrity auditor and behavioral proof;
3. auth behavior tests plus the genuine `UNKNOWN_NETWORK` fail-closed repair.

PR #762 is not reused as a broad red manifest. It is rebuilt around the only authoritative target: supervised, read-only MEG shadow operation after PR #763, PR #771, and PR #772.

## QA / Safety Review

The offline runner executes eight required groups on one SHA:

- authentication and startup;
- feed/subscription truth;
- persistence and shutdown;
- MEG observation;
- authority, ranking, and UI truth;
- manual approval and broker/order firewall;
- restart and reconciliation;
- AI reliability and evidence integrity.

The runner fails on missing tests, nonzero return codes, timeouts, or malformed results. The final certificate remains pending until the market-hours evidence certificate passes.

## Acceptance Proof

Acceptance requires:

- all selected PR #761 files remain inside the curated allowlist;
- the auth patch is limited to network-error classification and `UNKNOWN_NETWORK ok=false`;
- all eight offline gate groups pass on the final immutable SHA;
- test-integrity audit passes without weakening or suppressing tests;
- PR #771 and PR #772 remain green and in the exact stack ancestry;
- no protected runtime/feed/MEG/broker/strategy path changes beyond the declared auth file;
- final repository governance, security, and changed-path checks pass.

## Runtime Proof Required After Merge

The final certificate can become `MEG_SHADOW_SYSTEM_CERTIFIED_READ_ONLY` only after a fresh governed market session proves:

- authentication and startup success;
- actual post-mode FULL NIFTY packet delivery;
- subscription truth and constituent coverage;
- completed constituent bars and MEG traversal;
- canonical executable/advisory/blocked UI partitions;
- no fallback capital or executable ranking;
- clean persistence drain, shutdown, and restart evidence;
- no broker write or order authority;
- a passing PR #772 post-market reliability certificate.

## What This PR Does Not Prove

This PR does not prove strategy profitability, structural edge, expected returns, executable historical fills, paper/live trading permission, broker connectivity, production deployment, or unattended autonomous trading.

## Human Approval

Keep this PR draft until all offline gates are green, PR #763 passes its fresh live session, the final read-only certificate is generated and reviewed, and a human confirms the project remains advisory-only with no order authority.
