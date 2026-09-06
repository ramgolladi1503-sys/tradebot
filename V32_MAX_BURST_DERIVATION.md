# V32 maximum burst derivation

MAX_BURST_DERIVABLE=false
MAX_BURST_BETWEEN_CHECKS_BYTES=UNKNOWN

Queue item counts exist, but serialized item sizes, WAL transient growth,
concurrent writers, and atomic artifact maxima are not all bounded.
