# Feed Forensics Instrumentation Review

## Agent Work Contract

- source_agent: Codex
- action: observational instrumentation
- title: persisted feed-stall forensic ledger and classifier
- requested_paths: `core/feed_forensics.py`, feed callback/runtime/recovery hooks,
  status/classifier scripts, focused tests, and this review
- allowed_paths: those paths only
- forbidden_paths: strategy, MEG semantics, ranking, risk, credentials,
  broker/order behavior, subscription universe, instrument master, and restart
  thresholds
- expected_tests: fault-injection classifier tests, multi-cycle #803 controls,
  existing feed/persistence tests, eight-gate verifier, compile, diff check

## Scope Guard

The ledger records existing runtime facts and never changes decisions. It is
disabled by default, sampled at bounded intervals, append-only, and uses null
for unavailable values. The classifier is offline/read-only and does not create
a second authority system.

## Grill Me Review

Process liveness alone is intentionally insufficient. Missing callback,
persistence, watchdog, or recovery evidence produces `UNKNOWN`; the classifier
does not infer zeros or claim broker silence without causal evidence.

## Hermes Review

The canonical ledger carries session/producer identity, callback progress,
FULL-packet progress, tick/depth/runtime persistence progress, watchdog state,
and recovery lifecycle events. Existing runtime state is observed; thresholds
and recovery policy are untouched.

## GSD Review

The implementation adds one shared writer, two read-only commands, bounded
callback/progress hooks, recovery event observations, and deterministic fault
fixtures. It does not duplicate raw tick storage or alter feed/persistence
behavior.

## High-Risk Path Review

Feed/WebSocket hooks are observational `try/except` sidecars. A ledger write
failure cannot block or alter callback, subscription, restart, persistence, or
authority control flow. No broker API or order path is imported.

## QA / Safety Review

- Broker-write authority: false.
- Order authority: false.
- Paper/live authorization: false.
- High-frequency callback logging is sampled; no per-tick duplicate ledger is
  created.
- New fault-injection tests cover healthy, missing, writer-stall, watchdog,
  recovery-success, recovery-failure, and broker-silence evidence.

## Acceptance Proof

The final SHA must pass the eight-gate verifier, multi-cycle #803 controls,
feed/persistence regressions, compile, diff check, and this review gate before a
new live session.

## Runtime Proof Required After Merge

The next governed session must set `FEED_FORENSICS_ENABLED=true`, prove
advancing callback/FULL/tick/depth/runtime/watchdog evidence, and require at
least three MEG cycles with zero selected-tick reuse.

## What This PR Does Not Prove

It does not prove feed availability, broker reliability, strategy edge,
profitability, execution viability, or paper/live readiness.

## Human Approval

Human approval remains required before the next live observation. No main merge
or execution-authority change is authorized by instrumentation.
