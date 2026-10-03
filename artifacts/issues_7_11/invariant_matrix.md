# Invariant matrix — Issues 7–11

| Invariant | Evidence/check | Status |
|---|---|---|
| Broker/order/paper/live authority remains closed | Safety fields in observer outputs and tests; no broker/order API path added | PASS for inspected offline scope; live unverified |
| Missing T-1 data never becomes zero/PASS | frozen prerequisite loader and anti-fabrication tests | PASS fail-closed; source availability UNKNOWN |
| CAS values require immutable exact source-event identity | primitive verifier and heritage loader; legacy records remain inadmissible | PASS fail-closed; October interval UNKNOWN |
| Completed bars are persisted only after event-time completion and within session | store cutoff/session checks, source-time ingestion, MEG tests, and primary runtime restart integration | PASS for offline primary and MEG paths |
| Current runtime candle view never carries process-local bars across IST session dates | Issue 9 same-process D-to-D+1 rollover regression; prior-date store access remains explicitly date-scoped | PASS after bounded offline bridge filter; managed-service/captured parity unknown |
| MEG observer completed-bar output is bounded to requested IST date | D-to-D+1 shadow-buffer regression asserts exact timestamp set and unchanged local buffer | PASS offline; captured/deployment parity unknown |
| Supported 5-minute bars survive restart without a second persistence authority | Fresh-store-reopen test derives exact 5-minute OHLC/time boundaries from persisted complete 1-minute rows | PASS offline; only canonical 1-minute bars are stored |
| Primary C1/C2 memory can restore after process-local state loss | `test_normal_trusted_tick_restart_path_hydrates_c1_from_durable_bars` with a reopened store and cleared singleton buffer | PASS offline; actual service restart/captured parity unknown |
| Restored bars cannot prove current feed/session liveness | C1/C2 integration independently requires current `valid`, `time_sanity.ok`, live source, and bounded LTP age | PASS for offline path |
| Advisory missing/empty/error/partial inputs remain distinct | source reader tests including invalid UTF-8 and partial append | PASS offline |
| Observer advisory source equals its run-scoped writer ledger | explicit path binding and EOD fixture comparing source path, SHA-256, valid row count, and advisory IDs | PASS offline; captured/live parity unknown |
| Observer-only spot snapshot can consume exact fresh spot evidence while unrelated option aggregate is degraded | shadow adapter tests with explicit healthy transport/global-false scope | PASS only for the read-only observer consumer; no candidate/evaluator isolation claim |
| Stale required option and shared transport failure remain blocked | edge43/edge45 tests and observer blocker tests | PASS for tested caller contracts; classifier retains aggregate baseline semantics |
| Candidate-level cross-root option-health isolation and central consumer dependencies | no complete candidate pipeline fixture; shared classifier was intentionally left unchanged | UNKNOWN / incomplete |
| Configured token universe is not hard-coded by these changes | dynamic coverage/budget regressions | PASS tested config behavior; live env value unknown |
