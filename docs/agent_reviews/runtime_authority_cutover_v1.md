# Agent Review — Runtime Authority Cutover V1

## Agent Work Contract

- source_agent: ChatGPT
- action: `PROMOTE_RUNTIME_AUTHORITY`
- base: PR #763 head `1241418cafbefba8fd3d1142e5ae578d9b97cd70`
- scope: post-PR763 candidate selection, authority projection, operator UI, runtime snapshots, and execution-router firewall
- forbidden: feed, WebSocket, subscription, persistence, Market Event Graph, strategy thresholds, broker placement, and order actions

## Scope Guard

This PR is stacked on PR #763 and does not change the PR #763 branch. The implementation is limited to canonical authority modules, the existing opportunity selector, the runtime snapshot projection, the UI table model, the execution-router preflight, focused tests, and documentation. Feed, WebSocket, persistence, and Market Event Graph paths are unchanged.

## Grill Me

- Could a high-confidence fallback row still reach selection? No. Every input is normalized before the legacy selector, and only candidates whose canonical state is `EXECUTABLE` are passed to it.
- Could an advisory row retain a useful analytical score? Yes. `diagnostic_score` and `opportunity_score` remain available, but `selection_score`, capital allocation, and execution flags are forced to zero/false.
- Could a selected candidate bypass the authority layer later? Stamped candidates are checked again inside `ExecutionRouter` before approval or fill simulation.
- Does this replace PR #763 live proof? No. It is downstream authority hardening and does not certify packet delivery, constituent bars, or MEG traversal.
- Does it add live order capability? No. The existing live broker path remains unimplemented and this PR adds no broker write call.

## Hermes

The evidence chain is explicit and reviewable:

```text
candidate fields
→ immutable canonical execution decision
→ runtime authority stamp
→ executable-only selector input
→ normalized selected result
→ runtime snapshot/UI authority fields
→ execution-router preflight
```

The same authority payload includes state, primary reason, blockers, contradictions, operator bucket, analytical scores, selection score, and a no-order-action marker. Tests exercise both mapping and object candidates and verify the selection and router boundaries.

## GSD

The change follows the smallest effective cutover instead of refactoring the legacy TradeBuilder or Orchestrator:

1. retain PR #757's immutable decision and authority taxonomy;
2. normalize candidates at the actual opportunity-selection choke point;
3. project the same truth into runtime snapshots and UI rows;
4. verify it again at the execution-router choke point;
5. preserve PR #763 and all feed/MEG behaviour unchanged.

PR #758's useful proof themes—fallback/stale blocking, contradictions, object support, deterministic behavior, and protected feed boundaries—are absorbed through tests rather than by adding a second competing authority system.

## QA/Safety

Focused proof covers:

- recovered fallback remains advisory-only;
- fallback, stale, unknown, missing, synthetic, and contradictory quote truth fails closed;
- non-executable LIVE candidates receive `selection_score=0`, zero capital, no slot, and no execution flags;
- executable candidates are ranked only against executable candidates;
- UI output exposes `TOP_EXECUTABLE`, `ADVISORY_ONLY`, and `BLOCKED_DEBUG` separately;
- the execution router blocks stamped authority failures before approval or simulation;
- the existing manual-approval contract remains in place;
- no broker call, live process, or order action is performed by the tests.

## Acceptance Proof

Acceptance requires all of the following on the final immutable head:

- focused authority, selector, UI, router, and manual-approval tests pass;
- Python compilation passes for every modified runtime module;
- repository governance and security checks pass;
- changed-path review proves no feed, WebSocket, persistence, MEG, strategy-threshold, or broker-client change;
- temporary implementation machinery and unrelated runtime artifacts are absent;
- PR #763 remains at its verified head and is not rebased or modified by this PR.

## Runtime Proof Required After Merge

After PR #763 passes its governed market-hours session and this PR is rebased onto the resulting main branch, a supervised read-only shadow session must confirm:

- canonical authority fields appear in the runtime snapshots and UI;
- fallback/advisory/debug rows remain visible but cannot receive executable ranking or capital;
- any executable row carries fresh trusted quote truth and a positive selection score;
- no stamped non-executable candidate reaches approval or the execution router's simulation path;
- no regression occurs in PR #763 feed, persistence, shutdown, or MEG evidence.

## What This PR Does Not Prove

This PR does not prove PR #763's market-hours packet delivery, completed constituent bars, MEG traversal, strategy profitability, statistical edge, broker connectivity, real fills, production deployment readiness, or real-money execution safety.

## Human Approval

Keep this PR draft and unmerged until:

- PR #763 completes its fresh governed live proof;
- final-head CI and review evidence pass;
- a human reviews the authority fields, selector boundary, execution-router firewall, and changed-path scope;
- the branch is rebased onto the post-PR763 main branch without modifying protected feed or MEG paths.
