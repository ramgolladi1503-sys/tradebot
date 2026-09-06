# V33B startup fail-closed

The storage gate runs before `validate_authority`, `get_kite_client().profile()`, WebSocket setup, and observation start. Missing mount, ordinary internal directory, path escape, device mismatch, failed writable/temp/statvfs probe, or stat failure raises `StorageAuthorityError` and exits before network access. The launcher does not recreate `/Volumes/TradeBotData`.
