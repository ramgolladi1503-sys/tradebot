# PR #942 comparison

**Review point:** GitHub PR #942 head `678d87ffabfa1a2983adca0aa8382bfde22981b1`, base `main`; PR was open when inspected. No fetch, checkout, cherry-pick, merge, or remote mutation was performed. Its current check rollup included failures in `focused-contracts`, multiple `unit_tests`, `pr818-live-flow-freeze-target`, and Netlify checks.

| PR behavior | Classification | Evidence and rationale |
|---|---|---|
| `on_ticks` wall-clock one-second snapshot gate, with immediate bypass only when recovery is blocked | **SUPERSEDE** | Current repair gates before snapshot assembly using identity-aware 0.5-second cadence, admits safety identity changes immediately, and retains independent watchdog timer publication. The PR gate’s single recovery exception is narrower and does not cover all safety identity changes. This addresses duplicate snapshot assembly without reducing state freshness for safety transitions. Offline regression only; no production performance claim. |
| Shutdown drain minimum `max(10 seconds, remaining overall deadline)` for tick, depth, and runtime drains | **REJECT** | Imposes at least 10 seconds per sequential worker after the original overall deadline, potentially ~30 seconds across three drains. No measured backlog evidence or revised total shutdown bound supports this timeout floor. It masks the shared deadline semantics and can prolong shutdown. |
| Tick collector Parquet finalize/close, PAR1 footer warning, then 0.5-second wait and `os._exit(0)` | **REJECT AS AUTHORED** | Flush errors are swallowed by helper path, close errors are caught, `writer_closed` is set even after failed close, footer issue only warns, and process exits zero. Lock is not shared by ordinary writes/flushes. Added test directly uses PyArrow rather than the collector helper/lifecycle. Raw Parquet durability is orthogonal to this repair’s feed-health truth contract, but this implementation does not establish reliable finalization. |

## Decision

Do not adopt PR #942 as a unit. Its cadence concept is already covered more conservatively by this branch’s snapshot producer admission contract. The drain-floor and Parquet changes have unresolved shutdown/error semantics. PR checks were not green at inspection. No remote action taken.

Safety: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`.
