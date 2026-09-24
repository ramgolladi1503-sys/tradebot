# PR #932 Candidate Pipeline Repair

## Changes

- Candidate creation now requires the exact enabled CAS registry declaration,
  two identity- and integrity-verified primitive records, and a directional
  result from the canonical CAS evaluator.
- Generic confidence and completed-bar flags remain observation inputs only.
- Candidate qualification and feed freshness are separate states. Feed
  freshness is labeled advisory-only; this pipeline emits no executable
  candidates.
- Missing option prices remain null. Broker/order authority remains disabled.
- Telemetry counters are derived after strategy evaluation.

## Validation

The focused suite passed 16 tests. The unit fixtures are not market replay or
performance evidence. No replay or latency measurement was run against the
repaired source. Earlier replay artifacts used the pre-repair generic candidate
path and are superseded for qualification/execution claims.

## Scope

No broker adapter, order router, credentials, risk threshold, or live authority
was changed. Fresh exact-SHA CI and replay verification remain outstanding;
current verdict is `PR932_NOT_MERGE_READY`.
