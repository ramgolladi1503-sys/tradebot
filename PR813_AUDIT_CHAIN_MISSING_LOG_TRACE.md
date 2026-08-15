# PR813 audit-chain missing-log trace

Base authority: `ff8f8ae100b0424d40870d614bb025c93b32121f`

## Observed evidence

The failed session `pr813-live-20260814-092240` recorded `audit_chain:missing_log` in `runtime/logs/readiness_2026-08-14.json` and aborted before feed startup. Its resolved path was:

`<session DATA_ROOT>/runtime/logs/desks/DEFAULT/audit_log.jsonl`

The session lifecycle log shows `READINESS_GATE_RESOLUTION_CALLING` followed by `READINESS_GATE_RESOLUTION_ABORTED`; no audit bootstrap call occurred before readiness.

## Code path

- `config/config.py` defines `AUDIT_LOG_PATH` from the configured desk log directory.
- `core/audit_log.py` resolves `AUDIT_LOG`, creates GENESIS-linked records through `append_event()`, and rejects a missing path through `verify_chain()` with `missing_log`.
- `core/readiness_gate.py::run_readiness_check()` calls `verify_audit_chain()` and emits the blocker `audit_chain:<reason>`.
- `main.py` calls `core.runtime_bootstrap.ensure_runtime_dirs()` but, before this repair, did not initialize the audit chain before readiness.

## Lifecycle classification

`B) created by launch/bootstrap` is the established lifecycle. `append_event()` is the repository-native creator; a fresh session must create one legitimate event chained from `GENESIS` before readiness evaluates the chain. Existing logs are verified and never replaced.

## Root cause

`STARTUP_ORDERING_DEFECT=true`: readiness evaluated before audit-chain initialization. The file and parent directory were both absent in the fresh external runtime root; this was not a permission error or a wrong-worktree reuse.

The repaired bootstrap requires a nonempty `TRADEBOT_RUN_ID`, writes the session identity and boot epoch into a fresh bootstrap event, and independently verifies the resulting chain. A pre-existing invalid log remains fail-closed.

## Repair proof

- `MISSING_LOG_CHECK_LOCATED=true`
- `EXPECTED_AUDIT_LOG_PATH_KNOWN=true`
- `ROOT_CAUSE_CLASS=AUDIT_LOG_FILE_MISSING_AND_STARTUP_ORDERING_DEFECT`
- `RUN_ID_PROPAGATED_TO_AUDIT_PATH=true` (session root supplied by the launcher; run ID is also embedded in the bootstrap event)
- `AUDIT_LOG_SESSION_SCOPED=true`
- `AUDIT_LOG_CROSS_SESSION_REUSE=false`
- Fresh external bootstrap produced one `GENESIS`-linked event and `verify_chain()` returned valid.
- Short smoke reached orchestrator initialization without `audit_chain:missing_log`; it stopped at the independent `feed_runtime=MISSING_REQUIRED_FIELD` blocker.

No historical audit log was copied, no hash was hand-edited, and readiness validation remains fail-closed.
