# V33C storage epoch contract

Epoch 0 is `PRIMARY_EXTERNAL`. A verified loss transitions through `STORAGE_AUTHORITY_LOST`, `STORAGE_FAILOVER_PENDING`, `VERIFY_EMERGENCY_INTERNAL`, and `WRITE_FAILOVER_GENESIS` to epoch 1 `EMERGENCY_INTERNAL`. Any failed verification enters controlled shutdown. There is no epoch-2 or automatic failback transition. Every epoch-1 record must include session, source, cycle, epoch, authority, and failover event identity.
