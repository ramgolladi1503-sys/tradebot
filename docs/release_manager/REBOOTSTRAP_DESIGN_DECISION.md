# Design decision: no historical execution fallback

The forensic audit found no historical release authority that satisfies the post-PR-907 primitive trust boundary. Therefore V1 deliberately does not select an older SHA as a fallback. The recovery event retains the quarantined predecessor only as audit history and sets `fallback_live_sha=null` / `NO_TRUSTED_FALLBACK`.

This trades availability for truth. If the recovered authority later becomes unusable before another legitimate post-907 release exists, the system must fail closed rather than execute a quarantined historical authority.
