# V32 atomic-artifact bounds

Atomic replacement is used for several latest-state artifacts, but the source
does not establish maximum serialized payloads or concurrent atomic writers for
all runtime snapshots, seal, and post-close manifest paths.

ATOMIC_ARTIFACT_BOUNDS_COMPLETE=false
