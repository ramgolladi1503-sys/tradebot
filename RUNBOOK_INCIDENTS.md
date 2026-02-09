# Incident Response Runbook

## Severity
- SEV1: Trading blocked immediately
- SEV2: Pilot/live blocked, paper OK
- SEV3/SEV4: Logged, no automatic block

## Triggers
- Audit chain failure -> SEV1
- DB write failure -> SEV1
- Feed stale during market hours -> SEV2
- Hard halt -> SEV1

## Triage bundle
```
python scripts/incident_bundle.py --incident-id <id>
```

## Test trigger
```
python scripts/trigger_test_incident.py
```

## Verify audit chain
```
python scripts/verify_audit_chain.py
```

## Rollback
- Disable offending feature flag if applicable
- Restore from last known good DR bundle
