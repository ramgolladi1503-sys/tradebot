# TradeBot Repo Forensics Audit Checklist

Use this checklist for each post-code repo-forensics audit.

## 1. Entrypoints

- [ ] `run_live.sh` exists or configured equivalent exists.
- [ ] `main.py` exists or configured equivalent exists.
- [ ] dashboard entrypoint exists when scoped.
- [ ] configured entrypoints are not stale.
- [ ] startup path does not silently fallback into unsafe mode.

## 2. Runtime Flow

Expected flow:

```text
auth
  -> feed
  -> instrument_resolution
  -> market_validation
  -> candidate_generation
  -> no_trade
  -> ranking
  -> risk
  -> execution_boundary
  -> evidence
```

Checklist:

- [ ] Feed path is statically reachable.
- [ ] Candidate generation path is statically reachable.
- [ ] No-trade layer is statically reachable.
- [ ] Ranking layer is statically reachable.
- [ ] Risk layer is statically reachable before execution boundary.
- [ ] Evidence writing/reading path is identifiable.
- [ ] Any unproven step is marked `UNKNOWN`, not `PASS`.

## 3. Critical Modules

- [ ] Every configured critical module has a production caller or is explicitly marked deferred.
- [ ] Modules used only by tests are not treated as runtime-proven.
- [ ] Duplicate modules are flagged for ownership decision.
- [ ] Legacy active paths are identified.

## 4. Test Reality

- [ ] Shape-only tests are identified.
- [ ] Mock-heavy tests around safety/execution are identified.
- [ ] Negative tests exist for unsafe behavior.
- [ ] Evidence contract tests exist where scoped.
- [ ] Runtime wiring tests exist where scoped.
- [ ] Test failures are not hidden by weakening assertions.

## 5. Safety Boundaries

- [ ] SIM cannot call real broker placement.
- [ ] PAPER cannot call real broker placement.
- [ ] LIVE requires explicit readiness gates.
- [ ] Read-only modules do not expose order actions.
- [ ] Dashboard does not expose order actions unless explicitly scoped.
- [ ] `is_order_action=false` is preserved where required.
- [ ] `broker_api_called=false` is preserved where required.

## 6. Evidence Quality

- [ ] Evidence contains `mode`.
- [ ] Evidence contains `candidate_id` where applicable.
- [ ] Evidence contains `decision`.
- [ ] Evidence contains `reason`.
- [ ] Evidence contains `i-s_order_action` where applicable.
- [ ] Evidence contains `b-roker_api_called` where applicable.
- [ ] Evidence can distinguish runtime proof from manually written notes.

## 7. Architecture Drift

- [ ] Duplicate pipelines are identified.
- [ ] Old/new strategy paths are identified.
- [ ] Dashboard readers match real runtime evidence paths.
- [ ] Docs do not claim inactive behavior.
- [ ] Multiple config owners are flagged.

## 8. Output Requirements

Each audit report must include:

- summary counts by severity
- top findings
- evidence references
- files implicated
- proof required
- unknowns
- next 5 fixes only
