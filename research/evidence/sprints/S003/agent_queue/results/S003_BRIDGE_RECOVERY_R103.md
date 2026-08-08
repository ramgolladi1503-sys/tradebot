## MROS S003 — Bridge recovery diagnostic R103

- Persistent updater: `RUNNING`; last exit code `0`
- Persistent supervisor: `RUNNING`, but health is `HARD_STOP`
- Persistent worker: `RUNNING`, but health reports `BLOCKED`
- Local bridge HEAD: `1de75f9cb6c1742df20c0aebfe1f7fdf01cc99cd`
- Remote bridge HEAD: unavailable; `git ls-remote` failed because `github.com` DNS/network access is unavailable
- Authority HEAD: `b77638c4ae3d3d929dbe3798479b54f4e19d2c60`
- Queue HEAD: `91474e13c5e6dc3c8c26a839b010245b677f4cd4`
- Authority candidate/head: `9378d3f6ff9d27b603c406b695367ae8232b5451`
- State path: user-owned `madhuram:staff`, mode `755`; lock/log/health files user-owned, mode `644`; no immutable flags or ACL entries observed
- Repair performed: `NO`
- Exact blocker: updater stderr reports repeated `No space left on device` while updating bridge files
- Final supervisor health: `supervisor_status=HARD_STOP`, `last_error=WorkerError:REQUEST_FIELDS_UNKNOWN:controller_transport,transport_retry`, `runtime_authority=NONE`

Required operator action: free sufficient disk space, then kickstart the updater and supervisor and re-verify bridge and health state. No permission change is justified.

**Verdict: `AMROS_BRIDGE_OPERATOR_BLOCKED`**