# WebSocket Feed Remediation Handoff — 2026-10-01

## Source changes

The isolated remediation worktree contains a source patch for three observed feed issues:

1. Governed launch-plan option metadata now reaches the active WebSocket activation function, after exact reconciliation of production resolution rows, production tokens, and declared option counts/minimums. The module had duplicate activation definitions; the prior active definition shadowed the metadata transfer.
2. Empty option verification scope is now `FAILED` with `no_required_option_symbols`; it cannot publish an automatic verification success.
3. Runtime snapshots declare that `feed_ok` is a symbol aggregate and state whether a global transport/recovery block exists. Symbol-specific consumers may ignore an unrelated aggregate degradation only when global block is explicitly false, WebSocket is connected, and the evaluated symbol has complete blocker/freshness evidence. Whole-feed health still reports the degraded symbols.

The change does not adjust authentication, token selection, subscription budgets, minimum option coverage, freshness thresholds, ranking rules, or order/execution behavior.

### Follow-up root-cause correction

After the initial patch, a read-only review of the active source and October 1 session logs confirmed a regression: `build_subscription_tokens()` called strict full-plan activation with an intermediate observation-merge mapping that omitted `production_resolution`. That call cleared the symbol maps before the builder serialized its final per-symbol resolution, causing every option count to become zero. The follow-up local patch changes that intermediate call to update only observation-plan state, preserving the token identity that the builder has already resolved. Full launch-plan activation still rejects malformed authoritative metadata.

## Evidence and current limits

The read-only live artifact at 2026-10-01 12:08:56 IST showed a connected WebSocket, 97 option tokens, and `feed_ok=false` / `feed_truth_state=DEAD`; the current launch plan budget was 150 total tokens across 53 underlying symbols. Resolved option counts were below the configured per-symbol minimum of 12. The budget cannot satisfy all 53 minima (`53 + 53*12 = 689` total tokens before observation additions). That is a separate capacity/configuration decision and is not changed here.

The reconnect verification at 12:08 showed 53 symbols passing its short tick window, but this does not establish continuous freshness or eligibility. This patch cannot create missing ticks, solve under-coverage, establish provider capacity, or prove candidates now flow end-to-end.

## Safety status

- Existing live PIDs and their deployed checkout were not changed, signaled, restarted, or killed.
- The five PIDs supplied later (78795, 78774, 78775, 78757, 38882) were absent on a subsequent read-only process check. This does not prove why they exited.
- No broker API, order API, credential, or secret was accessed.
- No deployment or live verification was performed.
- New code is read-only with respect to trading actions; it does not enable live execution.

## Verification

Command:

```bash
/opt/anaconda3/bin/pytest -q tests/test_kite_depth_ws_stability.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_edge43_feed_health_truth.py tests/test_feed_00_canonical_feed_truth.py
/opt/anaconda3/bin/pytest -q tests/test_depth_subscription_tokens.py
```

Result: **124 passed** across feed health, canonical truth, WebSocket stability, and observation tests; an additional 17 direct subscription-token tests passed. `git diff --check` passed. Two environment dependency-version warnings were emitted for `numexpr` and `bottleneck`.

## Controlled rollout

1. Keep current live session untouched; this worktree is not deployed.
2. Before any later deployment, confirm a governed token plan can satisfy all configured per-symbol minimums within confirmed provider and system capacity. Do not lower the minimum or widen provider assumptions to force a pass.
3. Review and merge/deploy only in an operator-approved session after the active run ends; then run the established read-only readiness and feed validation gates.
4. Confirm auth state, WebSocket transport, requested/subscribed token maps, per-symbol option tick ages, feed truth, and end-to-end candidate ranking independently. Keep symbols/candidates blocked when any coverage or freshness gate fails.
5. Do not treat reconnect-window verification alone as live readiness. Do not enable order execution based on this source patch.

New config keys: none.
