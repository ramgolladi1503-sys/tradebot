# V33C SQLite failover model

`SQLITE_FAILOVER_MODEL=NEW_DB_EPOCH` is the selected model. The open external SQLite/WAL database is never copied or moved across devices. After successful genesis, a new internal epoch database may be initialized with session/source/candidate/epoch/failover lineage. Full continuation remains gated on bounded internal reserve and source-volume survivability.
