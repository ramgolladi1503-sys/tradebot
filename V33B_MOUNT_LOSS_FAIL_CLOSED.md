# V33B mount-loss status

Startup mount/device loss is executable and tested through `establish()`. Mid-session revalidation is now called once per observer loop and requests governed stop on loss. The shutdown report marks `final_seal=UNAVAILABLE_DUE_STORAGE_LOSS`; it does not claim a successful seal. No internal fallback is used.

`MOUNT_LOSS_FAIL_CLOSED_PASS=true` for the implemented observer lifecycle path; broader fault-injection coverage remains required before the full V33 continuation gate can pass.
