# Work Item: BUG-PR987-R4-WAL-SIDECAR-COLLISION-001

## Identity

- Work Item ID: `BUG-PR987-R4-WAL-SIDECAR-COLLISION-001`
- Type: `BUG`
- Parent Epic: `EPIC-APM-WAL-DURABILITY-001`
- Parent Feature: `FEAT-APM-WAL-OWNERSHIP-001`
- Title: Prevent an APM WAL from replacing another WAL's lock sidecar
- Current State: `IN_DEVELOPMENT` (QA verification is blocked; no acceptance transition recorded)
- Priority: `CRITICAL`

## Requirement Source

User request: `Sentinel PR #987 — R4 WAL Ownership Correctness` (current conversation). Product Owner accepted the narrow technical scope. The local hierarchy was created under the user's authorization because no canonical parent IDs were available.

## Current Behavior

For WAL `trade.json`, the manager locks `trade.json.lock`. A second process can open `trade.json.lock` as its own WAL and replace that pathname during atomic persistence. A third process then locks the replacement inode while the first process still holds the original inode.

## Expected Behavior

All supported aliases of one WAL resolve to one stable ownership identity. A WAL cannot name or replace an ownership lock object. Unsupported hard-link WALs, unsupported filesystems, and lock failures fail closed before recovery/admission.

## In Scope

- `core/active_position_manager.py`
- `tests/unit/test_apm_wal_process_ownership.py`
- This work item, its evidence record, and `PR987_R4_WAL_OWNERSHIP_VERIFICATION.md`.

## Out of Scope

- Other CodeRabbit findings, including unrelated APM lifecycle, OR trust, or recovery behavior.
- Strategy, levels, thresholds, broker/order paths, credentials, LIVE configuration, deployment, commits, pushes, merges.

## Acceptance Criteria

- Before/after behavior is demonstrated with independent processes and captured dev/inode identities.
- Collision attempt fails before mutation; third owner cannot acquire while original owner is alive.
- Alias, atomic replace, crash/recovery, and unsupported lock cases are covered offline.
- R3 regression commands, exact hashes, failures, and skips are reported; no full-suite pass is claimed.
- Smoke `IN_FLIGHT` failure is analyzed without relaxing OR evidence trust.
- APFS test results are not represented as deployment-filesystem proof.

## Allowed Paths

- `core/active_position_manager.py`
- `tests/unit/test_apm_wal_process_ownership.py`
- `docs/tradebot_delivery/work_items/EPIC-APM-WAL-DURABILITY-001.md`
- `docs/tradebot_delivery/work_items/FEAT-APM-WAL-OWNERSHIP-001.md`
- `docs/tradebot_delivery/work_items/BUG-PR987-R4-WAL-SIDECAR-COLLISION-001.md`
- `governance/evidence/CLAIM_REGISTRY.json`
- `governance/evidence/SOURCE_REGISTRY.json`
- `governance/evidence/work_items/BUG-PR987-R4-WAL-SIDECAR-COLLISION-001.json`
- `docs/agent_reviews/pr987-r2-controlled-remediation/PR987_R4_WAL_OWNERSHIP_VERIFICATION.md`

## Forbidden Paths / Actions

- Broker/order APIs and live runtime/processes.
- Credentials, secrets, environment files, strategy thresholds, risk gates, deployment, commit, push, merge.
- Any path outside the allowed list without a revised design and authorization.
