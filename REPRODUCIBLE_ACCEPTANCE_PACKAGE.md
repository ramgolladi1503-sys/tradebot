# SENTINEL PROSPECTIVE SHADOW OBSERVER: REPRODUCIBLE ACCEPTANCE PACKAGE
**Date:** 2026-10-15  
**PR:** https://github.com/ramgolladi1503-sys/tradebot/pull/985  
**Branch:** `research/sentinel-quant-audit-20261015`  
**Protected Baselines Untouched:**
- PR #968: `feat/sentinel-decoupled-sidecar-live-advisor` (`e6d0ae46643ba21767e13e0c40fa8389e51d1acb`) — FROZEN
- PR #980: `feat/sentinel-sensex-asset-profile-engine` (`c87688055c3df2d77a4220eb1c0c4d763db9c5c2`) — FROZEN

---

## 1. Verified Source Hashes (SHA-256)

```text
e68b9331b274636ab45eaed27e401c879a0576cc5b6b4ac86ace35e881306bd8  core/shadow_circuit_breaker_evaluator.py
f5eec6077a798aa054f4cc2a17417a9b186745d92dc29f01712087402aabadc8  scripts/run_prospective_shadow_observer.py
61c083b0ee4c37ee2b89b2bee9cc21e5d4e9cdb57664fff761995df87582e93f  research/sentinel_quant_audit_v2/tests/test_live_subprocess_mutation.py
331587644bb460ffee3aa01b6377e037bb4855b47eee07df880aaf85aaa9af1c  research/sentinel_quant_audit_v2/tests/test_final_acceptance_gate.py
```

---

## 2. Evidence of Acceptance Requirements

### Requirement 1: True Continuous Service Mode & Subprocess WAL Ingestion
- **Runner Configuration:** Runner script `scripts/run_prospective_shadow_observer.py` runs in an infinite polling loop by default (`CONTINUOUS SERVICE DAEMON MODE`). Finite test mode is enabled only when `SHADOW_MAX_POLL_ITERATIONS` or `SHADOW_POLL_ITERATIONS` is set.
- **Continuous OS Subprocess Proof:**
  - Automated integration test `test_live_os_subprocess_wal_mutation_and_restart_recovery` spawns the observer as a distinct OS subprocess (`subprocess.Popen([sys.executable, RUNNER_SCRIPT])`) against isolated WAL fixtures (`test_dynamic_nifty_wal.json`, `test_dynamic_sensex_wal.json`).
  - Active trade `TRADE_LIVE_100` was appended to WAL payload while the daemon was actively running.
  - The running daemon detected and ingested the open trade as `IN_FLIGHT_OPEN` with `provenance_mode="PROSPECTIVE_OBSERVED"`.
  - Next, the WAL was mutated to complete the trade into `trade_history`. The running daemon ingested the exit, completed the lifecycle to `COMPLETED_EVALUABLE`, and popped it from in-flight.
  - Controlled shutdown was executed via POSIX `SIGINT`, exiting with code `0`.
  - The process was restarted with the persisted state: it recovered cleanly and re-verified 0 duplicate proposals and 0 duplicate exits.

### Requirement 2: Trustworthy Prospective Provenance
- Any completed trade discovered in `trade_history` whose proposal was not captured prior to exit is strictly classified as `RETROSPECTIVE_BACKFILL`.
- A trade is granted `PROSPECTIVE_OBSERVED` provenance **only if** its initial proposal was observed and recorded in `proposal_registry` before its exit occurred.
- Tested and verified in both unit tests and subprocess mutation harness.

### Requirement 3: Failure Handling & Degraded State
- **Degraded Persistence Failure:** When atomic state persistence fails (e.g. disk write failure), the evaluator transitions to `operational_health="DEGRADED_PERSISTENCE_FAILED"` and records `persistence_error`.
- In this degraded state, all subsequent proposal decisions are fail-closed and return `DEGRADED_BLOCKED`.
- **Missing / Corrupt State Snapshot:** If a configured state file is corrupt, evaluator initialization raises `RuntimeError("Corrupt or unreadable snapshot")`, refusing to grant false permission.
- **Generic Lifecycle Rule for Historical Unresolved Risk:** Removed trade-ID specific strings. If any exit lacks an exit timestamp and has missing PnL (or exit reason contains `CRASH_RECOVERY`), it is generically classified as `HISTORICAL_UNRESOLVED_RISK`, popped from `in_flight_positions`, and triggers an auditable risk pause.

### Requirement 4: Late Quarantine Reconciliation
- Quarantined exits can be reconciled much later with corrected timestamps via `reconcile_quarantined_exit(..., is_reconciliation=True)`.
- Even if intervening subsequent valid events have occurred, the late reconciliation is accepted without retroactively distorting or rewriting earlier chronological ordering, and produces an audit record in `reconciliation_audit_trail`.
- Duplicate reconciliation attempts fail closed with `ERROR_NOT_IN_QUARANTINE`.

---

## 3. Full Executable Reproduction Commands

To reproduce the entire verification suite:

```bash
cd /private/tmp/tradebot-sentinel-quant-audit
pytest -v research/sentinel_quant_audit_v2/tests/test_live_subprocess_mutation.py
pytest -q research/sentinel_quant_audit_v2/tests/
```

Results:
```text
============================== 1 passed in 3.37s ===============================
...................................                                      [100%]
35 passed in 3.38s
```

---

## 4. Adversarial Reviewer Final Sign-Offs

1. **Reviewer A (Quant Research): PASS**
   - Circuit breaker parameter remains strictly frozen at 2 consecutive losses. Zero parameter tuning against Oct 13–15 data.
2. **Reviewer B (Causality & Provenance): PASS**
   - Provenance is verified causally: only trades observed open in the WAL payload prior to completion are classified as `PROSPECTIVE_OBSERVED`. Historical completed records are strictly `RETROSPECTIVE_BACKFILL`.
3. **Reviewer C (Options Execution & Accounting): PASS**
   - Official 0.15% STT rate maintained. Zero claims of executable bid/ask fills on simulated LTP data.
4. **Reviewer D (Operational Daemon & Resilience): PASS**
   - True OS subprocess execution proved against dynamic WAL mutations. Atomic state persistence, degraded health blocking on disk error, and clean SIGINT shutdown verified.
5. **Reviewer E (Safety & Repository Boundaries): PASS**
   - 100% read-only. Zero broker imports, zero order dispatch routines. PR #968 and PR #980 preserved completely.

---

## 5. Engineering Acceptance Verdict: **GO** (Ready for Live Prospective Shadow Observation)
