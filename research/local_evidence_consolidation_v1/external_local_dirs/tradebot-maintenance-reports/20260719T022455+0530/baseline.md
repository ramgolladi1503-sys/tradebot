# Baseline

- Timestamp: `2026-07-19T02:24:55+05:30`
- Shared checkout: `/Users/madhuram/tradebot`
- Shared checkout policy: protected/read-only for this task
- Initial free space: `2699432 KiB` (`2.57 GiB`)
- Latest free space observed: `3771376 KiB` (`3.60 GiB`)
- ORB outcome release gate: `>=20 GiB`
- Gate result: `FAIL`

PR state:

- PR #673: `MERGED`, head `c9c653110d6558f750914914b566f3f4928ed2a9`
- PR #674: `OPEN`, head `2219b0a6aa7294e2ff4124a80b5c7b182bd220ca`

Primary blockers:

- Disk is far below the required `20 GiB` pre-run gate.
- `/Users/madhuram/tradebot/main.py` is running from the shared checkout.
- Safe automatic reclaim candidates are too small to make the outcome run viable.
