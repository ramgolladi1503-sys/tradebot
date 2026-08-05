# Depth Persistence Diagnosis

Campaign `meg-dual-provider-20260805-04`, run `ada91c0ba82d-29a777589e3b`.

## Verdict

`WORKER_THROUGHPUT_INSUFFICIENT`

The preserved run accepted 4,794 depth rows, persisted 3,393, left about 1,400 queued, and rejected 1,239. No write exceptions occurred. The implementation had one worker and performed one SQLite transaction per row. The measured capture window was 66.870446 seconds: input was 71.69 rows/second and durable output was 50.74 rows/second, leaving backlog growth of 20.95 rows/second. At that rate a 2,048-row queue saturates in about 97.75 seconds; draining 1,400 rows at the measured durable rate takes about 27.59 seconds, far beyond the two-second shutdown deadline.

This is not a queue-capacity-only defect. The repair batches ordered rows into one SQLite transaction and drains accepted rows before worker termination. Schema, row order, timestamps, provider fields, and read-only authority are unchanged.

## Failed-run evidence

`shutdown_drain.json` records `worker_alive=true`, `complete=false`, `rejected=1239`, and `failures=0`. Tick and runtime persistence drained successfully. The failed evidence root remains unchanged.
