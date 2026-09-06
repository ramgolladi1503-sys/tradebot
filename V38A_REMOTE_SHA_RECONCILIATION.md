# V38A remote SHA reconciliation

DATE=2026-09-06
VALIDATED_CANDIDATE_SHA=73eb9e1d5b964de52924faa26e2fafb36d5d946a
REPORTED_REMOTE_SHA=48e67c87b1467ff986f39f41df68052334cfbfa0
REMOTE_SHA_EXISTS=true
REMOTE_SHA_DESCENDS_FROM_VALIDATED_CANDIDATE=true

The reported package SHA is a descendant of the validated candidate. Its
candidate-to-package diff contains 15 added V38 governance, manifest,
authorization, and documentation artifacts only. No runtime-source, strategy,
risk, feed, subscription, or broker behavior changed.

The package SHA is therefore not used as the runtime-source SHA. The exact
runtime ref is separately published at
`verification/cas-readonly-runtime-v37-73eb9e1-20260906`, resolving exactly to
the validated candidate.
