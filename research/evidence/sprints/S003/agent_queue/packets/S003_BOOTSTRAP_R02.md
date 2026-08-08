# MROS S003 Board Bootstrap Review — R02 Negative-Control / Fail-Open Attack

Review only exact candidate `5c7c0d6a75e6b8b56362011fb89b66efa29a64b3` in fresh isolation. Do not repair. Attack malformed inputs, missing fields, invalid enums, stale/wrong SHA artifacts, fake independence, insufficient quorum, majority masking, mandatory UNKNOWN, and any path that could fail open.

Return ONLY valid JSON matching `scripts/mros/validate_review.py`: artifact_id `S003-R02`, sprint `S003`, round `R001`, candidate_head exact SHA, role `negative_control`, both independence booleans true, controlled verdict, findings with required fields, counts, evidence_refs. Do not read peer outputs.
