# V33C session classification

No live session was run, so no actual failover occurred. A future failover session must emit `SESSION_STORAGE_CLASSIFICATION=EXTERNAL_TO_INTERNAL_FAILOVER`, both epoch presences, explicit continuity status, `prospective_admitted=false` by default, and seal status `PASS|PARTIAL|FAIL` without hiding the transition.
