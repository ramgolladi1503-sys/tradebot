# Daily live SOP

1. Run `./run_live.sh --read-only-observation`.
2. Resolve Kite authentication through the governed credential file/autologin.
3. Confirm runtime, feed, pipeline, dashboard, and persistence health.
4. Run only approved exact-SHA sidecars with isolated evidence.
5. At market close, stop, flush, seal, and confirm no respawn.

This is read-only market observation. It does not authorize orders or claim
fresh-session `LIVE_VERIFIED` without live evidence.
