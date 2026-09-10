# V31 malformed-file classification

MALFORMED_FILE_PRESENT_IN_F44E637=true
MALFORMED_FILE_PROVENANCE=PREEXISTING_BASE
MALFORMED_FILE_IMPORTED_BY_CANONICAL_LAUNCHER=false
MALFORMED_FILE_LIVE_PATH_REACHABLE=false
MALFORMED_FILE_CAS_PATH_REACHABLE=false
MALFORMED_FILE_SEVERITY=UNRELATED
MALFORMED_FILE_REPAIR_REQUIRED_FOR_SUCCESSOR=false
MALFORMED_FILE_REPAIRED=false

The file is syntactically malformed in the frozen base, but no repository
launcher or CAS path imports or references it. It is preserved rather than
repaired solely to make blanket compilation green. Scoped compilation of the
read-only launcher and reachable production modules remains the applicable
gate.
