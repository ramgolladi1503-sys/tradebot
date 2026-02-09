# Phase 12-14 Runbook

## Phase 12.1 Disaster Recovery
Verify:
```
python scripts/dr_backup.py
python scripts/dr_restore.py --bundle logs/dr_backup_<ts>.zip --target /tmp/restore_test
python scripts/dr_verify.py --state /tmp/restore_test
python scripts/dr_failover_drill.py --minutes 1 --paper
```

## Phase 12.2 Audit Chain
Verify:
```
python scripts/verify_audit_chain.py
python scripts/export_audit_bundle.py --out audits/bundle
```

## Phase 12.3 Incidents
Verify:
```
python scripts/trigger_test_incident.py
```

## Phase 12.4 Feature Flags + Canary
Verify:
```
python scripts/canary_status.py
python scripts/rollback_flags.py --dry-run
```

## Phase 13.1 Desks
Verify:
```
python scripts/desk_status.py
```

## Phase 13.2 Capital Committee
Verify:
```
python scripts/capital_committee_report.py --days 60
```

## Phase 13.3 Paper Tournament
Verify:
```
python scripts/paper_tournament.py --days 30
```

## Phase 14.1 Hypothesis Generator
Verify:
```
python scripts/generate_hypotheses.py
```

## Phase 14.3 Adaptive Risk
Verify:
```
python scripts/adaptive_risk_status.py
```

## Umbrella
```
python scripts/regression_gate_12_14.py
```
