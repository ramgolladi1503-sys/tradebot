# Simulation Report

Deterministic tests reproduce the captured shape without broker calls:

- current token inventory present
- callback activity continues
- partial activity is detected
- at least one token is stale

Expected repaired behavior:

- no terminal `RECOVERY_BLOCKED` from ordinary partial activity
- no false physical disconnect
- runtime state becomes `DEGRADED_LOCAL` when critical/core truth is not stable
- runtime state becomes `VERIFYING_RECOVERY` during stable verification
- one callback batch does not clear the degraded state
- three stable cycles clear the verification and return the runtime to `LIVE`
- stale critical tokens keep the runtime degraded

The simulation is intentionally local and read-only. It does not place, modify, cancel, or authorize broker orders.
