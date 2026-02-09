# Disaster Recovery Runbook

## What is backed up
- SQLite DBs (trade db, data/*.db)
- Config snapshot (`config/config.py`)
- Decision log (`logs/decision_events.jsonl`)
- Model registry (`logs/model_registry.json`)
- Daily audit artifacts

## Backup
```
python scripts/dr_backup.py
```
Output: `logs/dr_backup_<timestamp>.zip`

## Restore
```
python scripts/dr_restore.py --bundle logs/dr_backup_<ts>.zip --target /tmp/restore_test
```

## Verify
```
python scripts/dr_verify.py --state /tmp/restore_test
```

## Failover drill
```
python scripts/dr_failover_drill.py --minutes 1 --paper
```
Produces: `logs/dr_failover_drill.json`

## Rollback
- Remove restored target directory
- Re-run restore with the previous bundle

## Common failures
- `DR_DB_TABLES_MISSING`: DB schema incomplete or corrupt
- `DR_CHECKSUM_MISMATCH`: file modified or partial restore
- `DR_NO_DB_FOUND`: bundle missing DB files
