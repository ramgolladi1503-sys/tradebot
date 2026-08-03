# Agent Review — Runtime Authority Cutover V1

## Agent Work Contract

- source_agent: ChatGPT
- action: PROMOTE_RUNTIME_AUTHORITY
- scope: post-PR763 selection, UI, snapshot, and execution-router authority
- forbidden: feed, WebSocket, MEG, persistence, strategy thresholds, broker placement

## Scope Guard

The change is stacked on PR #763 and does not change its branch. Protected feed/MEG paths are forbidden. No live process or broker action is started.

## High-Risk Path Review

The execution router now consumes canonical authority only for candidates stamped by the cutover. This preserves existing legacy tests while ensuring every selected candidate is checked before manual approval or simulation. The LIVE broker path remains unimplemented and no order capability is added.

## Acceptance Proof

- recovered fallback is advisory-only and receives zero selection score/capital;
- stale, missing, unknown, synthetic, and contradictory truth fails closed;
- actual opportunity selector sees executable candidates only;
- operator rows are partitioned by authority;
- execution router blocks authority failures before order-state/approval work;
- protected feed and MEG paths remain untouched.

## What This Does Not Prove

This does not certify PR #763's market-hours packet/bar traversal, profitability, or live broker execution. Those remain separate gates.
