# TEP v1 Operator Runbook — Candidate

## Safety baseline
Broker write, order, paper and live execution authorities are DENY. Read-only observation is separately gated. Never use a dirty canonical checkout as integration authority.

## Start/restart
Bind to exact repository SHA and configuration hash. Open the transactional store, validate schema, acquire singleton ownership, then start supervisor. Restart must expire stale leases before scheduling work. Heartbeat proves liveness only.

## CI
Pending CI is passive. Terminal failures are classified baseline/candidate/environment/external/policy before repair. Do not wake workers for pending CI.

## Merge
Refresh current main and PR head/base/check/review state immediately before merge. Merge serially. After main advances, invalidate all previously cached merge readiness.

## Live observation
Use only a read-only adapter with a dated launch plan, dynamic subscriptions and runtime output outside source checkout. Stop by market-calendar/session contract, drain, close adapter and seal evidence. Observation PASS is not execution viability or edge.

## Failure
Database corruption, authority drift, protected-path uncertainty, unique-evidence uncertainty and unknown provenance fail closed. Preserve artifacts and emit a typed blocker.

## Recovery/rollback
Do not delete predecessor infrastructure during adoption. Every reused component requires source hash and rollback reference. Restore from immutable backup/export, verify IDs/hashes, then resume from durable state.
