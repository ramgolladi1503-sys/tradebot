# V33C emergency authority

The governed emergency family is `~/.tradebot/emergency-runtime/<session_id>/`. Preflight verifies realpath, directory type, non-external/non-checkout location, writable temp creation, and `statvfs`. It is never `/Users/madhuram/tradebot/logs`, cwd, `/tmp`, or `/private/tmp`.

Current implementation is available through `preflight_emergency_root()`; no live emergency root was created.
