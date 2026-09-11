# V32 disk-pressure shutdown/seal

DISK_PRESSURE_SHUTDOWN_SEAL_PASS=false

No implementation exists to execute the pressure transition. A synthetic
bounded persistence drain passed independently in V28, but that is not proof
of the V32 disk-pressure halt path or final seal under reserve exhaustion.
