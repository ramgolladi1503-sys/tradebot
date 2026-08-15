# PR813 audit integrity defect reproduction

Base SHA: `11855d1f5ea151c5b6639374b6d9a34f8dc6e482`

Before repair, a valid bootstrap event created under `RUN_A` was passed to `initialize_audit_chain(run_id="RUN_B")`; the existing-log path called structural `verify_chain()` without a current-run expectation and returned `ok=true`. A freshly touched empty file likewise returned `ok=true`, `count=0`, because the old validator accepted zero parsed records.

The repair requires the first event to be `AUDIT_CHAIN_BOOTSTRAP`, requires a nonempty `run_id`, rejects zero events, and passes the current run ID into validation. Existing prior-run logs now return `run_id_mismatch`; empty files return `empty_log`.
