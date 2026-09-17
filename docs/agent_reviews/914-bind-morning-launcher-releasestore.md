# Agent Review: PR #914 — Bind Morning Launcher to Certified ReleaseStore SHA

## 1. Intent and Scope
This PR binds the governed morning observer launcher (`GovernedMorningOrchestrator`) directly to the repository-owned `ReleaseStore` authority located dynamically at `storage_volume / "release_store"`.
Previously, omission of `--expected-sha` allowed any clean checked-out commit to pass release verification without validating against the governed `ReleaseStore.certified_live_sha`.

## 2. Invariants Preserved
- `ReleaseStore.certified_live_sha` is primary and mandatory.
- Missing, empty, or corrupt `ReleaseStore` blocks launch immediately.
- Running `git rev-parse HEAD` must match `certified_live_sha` exactly.
- Caller `--expected-sha` cannot override `certified_live_sha`.
- Uncertified commit fails closed before storage, auth, websocket, or observer execution.
- Single-command morning operator UX preserved.
- `broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`.
- Zero orders placed, modified, or cancelled.

## 3. Pre-CI Verification Summary
- Focused unit tests: 24/24 PASS (`tests/test_governed_morning_orchestrator.py`).
- Affected regression tests: 37/37 PASS across release stores and change impact suites.
- 25-class adversarial pre-CI attack campaign: 25/25 PASS.
- Required mutation scenarios: 8/8 detected.
- Whole-tree compilation and diff check clean.
