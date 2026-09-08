# V33B mirror disposition

All identified canonical-runtime repository-local mirrors are redirected by setting `REPO_LOG_DIR` to `<external runtime root>/logs` before runtime initialization. Historical files in `/Users/madhuram/tradebot/logs` are preserved and are not deleted or read as live authority.

`INTERNAL_MIRROR_DISPOSITION_PASS=true`
`BLOCKED_MIRRORS=NONE`
`REPOSITORY_LOCAL_LIVE_LOG_WRITES=0` under the governed launcher.
