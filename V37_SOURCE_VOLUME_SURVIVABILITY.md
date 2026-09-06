# V37 source-volume survivability

The external volume is the normal runtime authority. The successor is kept
on that volume and is not silently copied to internal storage before start.
The internal exact-SHA release image is permitted only after the final commit
and must be verified by hash. Mount loss remains fail-closed: no silent source
or evidence fallback is allowed.
