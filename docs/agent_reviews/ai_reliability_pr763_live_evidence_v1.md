# Agent Review — AI Reliability PR763 Live Evidence V1

## Agent Work Contract

- source_agent: ChatGPT
- action: `COMPLETE_AI_RELIABILITY_EVIDENCE_CHAIN`
- base: PR #771 runtime-authority cutover branch
- source: PR #760 additive reliability sidecar
- scope: sealed PR #763 evidence verification, authority-snapshot verification, deterministic post-market report
- forbidden: packet callbacks, feed mutation, strategy/ranking mutation, broker access, approvals, orders, and live-loop control

## Scope Guard

This change is an isolated read-only sidecar. It may read a completed evidence root and authority snapshot files after the session. It cannot subscribe to a feed, run a broker client, alter candidates, assign capital, approve trades, or place/cancel/modify orders. Source files copied from PR #760 are restricted to `core/ai_reliability_agent/**`, its scripts, tests, fixtures, architecture documents, and certification reports.

## Grill Me Review

- Can the agent declare a session valid from an unsealed directory? No. Missing or invalid `SEALED`, `artifact_manifest.json`, or `SHA256SUMS` fails closed.
- Can it ignore a modified artifact? No. Every declared artifact is checked for path safety, size, SHA-256, and exact manifest membership.
- Can advisory/fallback rows pass as executable? No. Authority snapshots are checked for bucket, state, allowed flag, selection score, capital, quote safety, and duplicate executable/advisory identity.
- Can it call a broker or influence the live loop? No. The new verifier is path-driven and post-market only; PR #760's LIVE tool registry also blocks non-read-only tools.
- Can it claim profitability? No. Strategy edge, profitability, and causal market explanations remain explicit exclusions.

## Hermes Review

The durable evidence chain is:

```text
PR #763 sealed root
+ SHA-verified artifact manifest
+ normalized live-proof observations
+ PR #771 authority snapshots
→ deterministic gates
→ JSON/Markdown reliability certificate
```

The report records each gate, evidence counts, errors, input hashes, and the strongest truthful verdict. Missing live semantics yields `IMPLEMENTATION_COMPLETE_LIVE_EVIDENCE_PENDING`, not success.

## GSD Review

The implementation reuses PR #760's evidence ledger, analytics, and component-certification sidecar. It adds only the missing system boundary: independent verification of PR #763 session evidence and PR #771 operator/execution authority. It does not add another runtime agent or duplicate the PR #763 recorder.

## QA / Safety Review

Focused tests cover:

- valid sealed-root verification;
- post-seal tamper detection;
- path traversal and undeclared artifact rejection;
- advisory/fallback rows never passing executable authority;
- non-executable selection score and capital forced to zero;
- explicit order/broker-write authority causing failure;
- incomplete live evidence producing a pending verdict;
- complete synthetic live semantics producing a read-only reliability pass;
- deterministic output across repeated runs.

## Acceptance Proof

Acceptance requires:

- PR #760 focused component, evidence, analytics, replay, and integration tests pass;
- new PR #763 session-verifier tests pass;
- all copied files remain inside the allowlist;
- no runtime/feed/MEG/strategy/risk/broker file is modified;
- temporary implementation files are absent from the final head;
- final-head repository governance and security checks pass.

## Runtime Proof Required After Merge

A fresh governed PR #763 market session must supply one new sealed evidence root and authority snapshots showing:

- actual post-mode FULL NIFTY packet delivery;
- completed NIFTY constituent bars;
- required Market Event Graph traversal;
- read-only operation with no order or broker-write authority;
- executable/advisory/blocked operator partitions obeying PR #771;
- clean shutdown, complete persistence drain, and immutable sealing.

The post-market verifier must then emit `PASS_READ_ONLY_POST_MARKET_RELIABILITY`. Until then, the strongest valid status is `IMPLEMENTATION_COMPLETE_LIVE_EVIDENCE_PENDING`.

## What This PR Does Not Prove

This PR does not prove strategy profitability, structural edge, historical execution quality, live broker connectivity, real fills, production deployment readiness, or permission for paper/live trading.

## Human Approval

Keep the PR draft and unmerged until PR #771 is green, the final changed-path scope is reviewed, all CI gates pass, and a human reviews the first real PR #763 post-market reliability certificate. The sidecar must remain read-only after merge.
