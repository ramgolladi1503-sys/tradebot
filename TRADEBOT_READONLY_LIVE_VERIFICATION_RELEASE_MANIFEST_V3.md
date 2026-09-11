# Read-only live-verification release manifest V3

Runtime source SHA: `fd00cbfb2ec06db2df4a5700aedfd93d17132bcf`
Verification ref: `verification/v38b-post-merge-integration-20260907`
Verification package SHA: `15c598dadc0838dbac0711dcf0bbe1e9a9608299`
Release image: `/Users/madhuram/.tradebot/releases/fd00cbfb2ec06db2df4a5700aedfd93d17132bcf`
Canonical launcher: `scripts/run_kite_read_only_observation_v1.py`
Market-state mode: `EXPLICIT_READ_ONLY_SIDECAR`

The integrated tree includes V37 storage/failover/CAS authority and PR #885 as
an execution-inert sidecar. The package is not live authorization. Fresh
authentication, market-data, CAS, persistence, and shutdown evidence remain
required in a separately authorized future session.
