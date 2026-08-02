# PR #763 Agent Review Evidence

## Agent Work Contract

Objective: make the unified live-validation branch observable and safe enough for an **observe-only** market session. The immediate repair in commit `0f0a836bdc4a4ea976c69c43f908bbea54b3ba99` corrects the offline reconnect resource-soak contract so it verifies transport lifecycle separately from production live-tick recovery.

The agent is authorized to inspect CI, make narrowly scoped fixes on the PR branch, add tests or evidence required by repository gates, and report exact limitations. It is not authorized to merge the PR, enable live order execution, weaken production feed safety, or claim strategy profitability.

## Scope Guard

In scope:

- PR #763 CI failures.
- Feed reconnect transport lifecycle, subscription replay, lock release, resource bounds, and evidence accuracy.
- Required review evidence for this PR.
- Observe-only readiness and fail-closed behavior.

Out of scope:

- Live broker order placement.
- Strategy threshold tuning or profitability claims.
- ML model training or promotion.
- Broad refactoring unrelated to a demonstrated failure.
- Merging PR #763.

## Grill Me Review

Adversarial questions applied:

1. **Did the patch merely suppress the recovery assertion?** No. It still requires a distinct websocket generation, connected transport, exact subscription replay, no terminal failure, no process-restart requirement, no recovery-blocked state, and no held reconnect lock. It then explicitly proves that the synthetic recovery owner can be released.
2. **Could the resource soak now certify live tick recovery without ticks?** No. The patch documents that live option-tick verification is outside this harness. Production verification remains in the feed runtime and is not modified by this patch.
3. **Could a same-generation reconnect pass?** No. Generation identity must change.
4. **Could partial or duplicate subscriptions pass?** No. Expected and actual token counters must match exactly.
5. **Could a terminal or blocked feed state pass?** No. Terminal failure, process restart required, and recovery blocked are explicit failure conditions.

## Hermes Review

The operational message is intentionally narrow:

- A green resource soak means repeated synthetic websocket generation replacement and exact subscription replay remained bounded in file descriptors, threads, locks, and reachable retired objects.
- It does **not** mean live market ticks resumed.
- It does **not** mean the full PR is ready to merge.
- Tomorrow's session must remain observe-only and must separately capture physical connection, tick freshness, subscription verification, fallback use, candidates, ranking, and UI/journal consistency.

## GSD Review

Execution sequence:

1. Reproduce and inspect the Feed Smoke failure.
2. Identify the mismatched test contract: a new connected generation existed, but the no-tick harness waited for production live-data verification to clear.
3. Separate transport/resource success from live-tick recovery without changing production runtime code.
4. Run CI and inspect any remaining failures.
5. Do not start ranking or ML work until the feed lane is trustworthy.

## QA / Safety Review

Safety invariants retained by the reconnect resource soak:

- New websocket generation is mandatory.
- Connected state is mandatory.
- Exact token subscription equality is mandatory.
- Terminal failure is forbidden.
- Process restart required is forbidden.
- Recovery blocked is forbidden.
- Reconnect lock must be released.
- Synthetic recovery owner release must succeed and be verified.
- File-descriptor, thread, queue, and retired-generation checks remain active.
- Negative leak controls remain expected to detect injected leaks.

Production safeguards were not relaxed. No execution or broker-order path was changed by commit `0f0a836bdc4a4ea976c69c43f908bbea54b3ba99`.

## High-Risk Path Review

PR #763 changes high-risk configuration, feed/WebSocket, orchestrator, and strategy paths. Therefore:

- The PR must not be merged solely because Feed Smoke passes.
- Production feed recovery still requires live evidence that fresh underlying and option ticks resume after a real disconnect.
- Any fallback or recovered quote must remain non-executable unless the canonical execution-truth gates independently establish fresh live data.
- Strategy and ranking outputs must remain advisory during the next live observation session.
- Existing fail-closed states such as terminal reactor failure, process-restart-required, stale feed, missing option feed, and subscription mismatch must remain visible and action-blocking.

## Acceptance Proof

Patch-level acceptance proof for `0f0a836bdc4a4ea976c69c43f908bbea54b3ba99` requires:

- Feed Smoke completes successfully.
- Reconnect stress creates distinct generations for every accepted cycle.
- Exact subscription replay remains true.
- Recovery owner is released after synthetic transport verification.
- No terminal failures or hard mismatches occur.
- Resource-growth and negative-control assertions remain effective.

PR-level acceptance additionally requires all mandatory CI gates to pass and an observe-only live evidence pack to show truthful feed, candidate, fallback, ranking, and UI behavior.

## Runtime Proof Required After Merge

Merge is not performed by this work. After any future authorized merge, runtime proof must include:

- Exact deployed commit SHA and configuration fingerprint.
- Successful physical Kite websocket connection.
- Fresh underlying and option ticks.
- At least one controlled reconnect or naturally observed disconnect/recovery sequence, with a new generation and verified subscription replay.
- No silent fallback promotion into an executable candidate.
- Candidate journal, ranking snapshots, fallback events, errors, operator actions, and session summary.
- Reconciliation between dashboard output and durable evidence artifacts.

## What This PR Does Not Prove

- It does not prove profitable expectancy.
- It does not certify any strategy for live capital.
- It does not prove that a real Kite/Twisted reactor can always be restarted in-process.
- It does not prove live option ticks recover after every disconnect.
- It does not prove ranking quality or score separation.
- It does not authorize automatic or manual live order execution.
- It does not prove the entire 319-file PR is defect-free.

## Human Approval

A repository maintainer, preferably Ram, must review the final CI state, the high-risk-path limitations above, and the observe-only live evidence before approving merge or any change in execution mode. This document records evidence and constraints; it does not grant approval.
