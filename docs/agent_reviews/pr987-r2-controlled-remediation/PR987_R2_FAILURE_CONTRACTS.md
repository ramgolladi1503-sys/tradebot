# PR987 Round 2 — Frozen Failure Contracts

These contracts were frozen before implementation from the attached remediation mandate, the Round 2 final audit, and separately produced BA/PO/Hermes/Grill/QA/T&Q inputs. They do not alter RBFN levels, thresholds, setup geometry, or trading eligibility.

## P0 — Streaming lock and OR reconciliation

- Neither the post-opening reconciliation path in `_update_spot_locked` nor the five-minute bar-close path may perform HTTP, retry, filesystem lock, ledger I/O, or wait operations while `self._lock` is held at any reentrant depth.
- Capture immutable session, event timestamp, generation, request identity, and retry context before scheduling. Use bounded, nonblocking enqueue and at most one outstanding request for the same session/index context.
- A worker may do ledger/network I/O outside the advisor lock. Before applying a response, reacquire the lock and require that its session, generation, outstanding request token, and freshness are still current. Late, malformed, duplicate, missing, stale, rollover, shutdown and retry-exhausted responses must fail closed without changing newer evidence.
- Existing retry budget/ledger semantics remain bounded. Both real `on_tick` call paths require event-blocked fake-client tests; direct helper tests do not satisfy this contract.

## P0 — Replay transport and dispatch isolation

- In replay mode, no injected or default network transport method may be invoked, regardless of token/client/adapter presence.
- Replay combined with automated dispatch or live flags must fail closed before constructing or invoking an execution-capable dispatcher.
- Replay still supports deterministic local fixtures. No test may reach a network socket, DNS, broker endpoint, order path, or credential source.

## P1 — Opening-range provenance

- `seed_opening_range_evidence` and test fixture helpers can create only `SYNTHETIC`/`REPLAY` provenance; they cannot make live OR evidence eligible even if a caller supplies a forged Upstox source label or coverage fields.
- Live complete evidence must be tied to the existing trusted ingestion/reconciliation path and its validated 30 normalized one-minute candle records, exact session coverage and persisted proof. Metadata flags or hashes alone do not authenticate an origin.
- Existing strict OHLC/date/duplicate/coverage/boundary validation stays in place. Valid offline historical fixtures must be explicitly offline; no test returns a LIVE_VERIFIED claim.

## P1 — APM position truth

- Spot/bar target touches are advisory target events, not fill confirmations. They cannot set a field that claims a tranche was booked, change actual remaining/filled quantity, or produce realized tranche PnL.
- No confirmed fill source was found in the scoped repository. Therefore actual fill and remaining quantities remain unknown/unchanged; derived target marks must be labelled as projections if retained.
- Preserve runner trailing behavior with a distinct target-reached/advisory state. Do not invent fill events, broker adapters, or actual partial executions. Existing 50/50 PnL blend must not be represented as realized execution accounting.
- Cover CE/PE and 1/2/3/4 lots, repeated target events, runner exit and WAL recovery. Partial/duplicate fill tests are applicable only if an authoritative read-only fill source is identified.

## P1 — APM WAL and recovery

- Corrupt, unreadable, inconsistent or failed recovery evidence must never become normal `STANDBY` with an unresolved position silently cleared. Use an explicit blocked/unknown recovery state and prove entry admission rejects it.
- Forced durability failure, including parent-directory open/fsync after replace, must be surfaced and leave in-memory state blocked/uncertain. Do not report success when durability is unknown.
- Document the `force_sync=False` debounce/checkpoint window. Test write, flush, file fsync, replace-before, post-replace/directory fsync, corrupt WAL, interrupted recovery and restart windows. Do not claim exchange-side exactly-once execution.
- APM WAL durability is separate from the OR reconciliation ledger; no guarantees transfer between them.

## P2 — Strategy history

- Existing focused test `test_mode5_bar_abstains_before_history_mutation_without_valid_or` requires OR-rejected bars not to enter strategy history. Current Round 2 code violates that test by appending first.
- Do not redesign or broaden RBFN lookbacks here. Restore the existing strategy-eligible-history boundary and retain raw observed bars separately only if a safe, isolated history field is needed. If current contract remains ambiguous, retain the existing tested behavior and record `BLOCKED_STRATEGY_CONTRACT` rather than changing eligibility.

## Out of scope

Strategy thresholds, TD/RP equations or levels, broker adapters, order actions, automated/live enablement, credentials, deployment, PR updates, merge, production processes, and market-edge claims remain untouched.
