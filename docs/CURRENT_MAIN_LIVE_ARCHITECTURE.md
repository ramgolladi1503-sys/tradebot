# Current-main live architecture

`run_live.sh` is the single product launcher. It validates the governed Kite
session, binds mutable state under `DATA_ROOT`, and `exec`s `main.py`.

`main.py` is the product runtime and UI entrypoint. Its normal path owns the
canonical feed, pipeline/orchestrator, analytics, persistence, and dashboard.
`scripts/run_kite_read_only_observation_v1.py` is a validation harness and
must not replace the product launcher. `scripts/run_live_observation.sh` is a
legacy wrapper and is not an operator entrypoint.

`--read-only-observation` keeps market-data mode available but explicitly
sets the read-only contract: no broker-write, order, paper, or live-execution
authority. Candidate generation and dashboard display remain possible;
broker execution is not.

Mutable runtime state is external to the source checkout. Credentials remain
under the governed private credential directory and are never copied into
runtime evidence.
