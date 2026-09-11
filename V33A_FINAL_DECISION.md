# V33A final decision

```text
EXTERNAL_VOLUME_EXPECTED=/Volumes/TradeBotData
EXTERNAL_VOLUME_REALPATH=/Volumes/TradeBotData
EXTERNAL_VOLUME_DEVICE_ID=16777240
EXTERNAL_VOLUME_FILESYSTEM=apfs
EXTERNAL_VOLUME_PRESENT=true
EXTERNAL_VOLUME_WRITABLE=true
EXTERNAL_VOLUME_DEVICE_AUTHORITY_PASS=true
RUNTIME_ROOT_DEFAULT=/Volumes/TradeBotData/tradebot-live-diskguard-successor-20260905/.runtime
RUNTIME_ROOT_DEVICE_ID=16777240
RUNTIME_ROOT_EXTERNAL_BOUND=true
TEMP_SAME_DEVICE_PROBE=true
INTERNAL_MATERIAL_WRITERS_IDENTIFIED=true
INTERNAL_MATERIAL_WRITERS_CLOSED=false
UNKNOWN_MATERIAL_WRITERS=false
ALL_MATERIAL_LIVE_WRITERS_EXTERNAL=false
MOUNT_LOSS_FAIL_CLOSED_SPECIFIED=true
MOUNT_LOSS_FAIL_CLOSED_EXECUTABLE_TESTED=false
V33_STORAGE_WORK_MAY_CONTINUE=false
V33A_EXTERNAL_VOLUME_AUTHORITY=PASS_WITH_INTERNAL_SPILL_BLOCKER
SUCCESSOR_COMMIT_ALLOWED=false
PR_ALLOWED=false
LIVE_RESTART_ALLOWED=false
BROKER_WRITE_AUTHORITY=false
ORDER_AUTHORITY=false
ORDERS_PLACED=0
```

Decision: the mounted external volume is proven as the runtime filesystem authority for the configured successor paths, but V33A is not complete because repository-local compatibility mirrors and untested mount-loss enforcement leave a live internal-spill path. V33 storage work must not continue until those controls are closed without inventing a reserve model.
