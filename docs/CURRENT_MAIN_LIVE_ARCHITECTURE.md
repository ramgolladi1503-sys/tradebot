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

At session start, `core.live_session_manifest` binds the source SHA, observer
SHA/PID, runtime and SQLite paths, current instrument-master identity, feed,
auth, persistence, and registered read-only consumers. Consumers must use
that manifest rather than discover stale processes or historical artifacts.
`core.live_lifecycle_contract` gates live verification on fresh ticks,
persistence, market primitives, strategy/option/ranking/advisory evidence,
one feed owner, and false execution authority. Close requires stop, flush,
and no-respawn evidence before sealing.

The consumer shape is one canonical observer feeding regime, strategies/CAS,
candidate/ranking, monitoring, and isolated sidecars. The UI remains a read
consumer of advisory output and does not become strategy or execution
authority.
