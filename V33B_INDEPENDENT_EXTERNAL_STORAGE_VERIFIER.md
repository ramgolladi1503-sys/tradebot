# V33B independent verifier

Independent checks rerun outside runtime self-report: `realpath /Volumes/TradeBotData`, mount table, `st_dev`, writable probe, same-device temp probe, configured successor paths, and manifest hash. Results: external volume present/writable, device `16777240`, runtime paths same-device, manifest `118` and SHA `5e4cbc...f3d4ecf292b1a67160910dc1822d81f75e60f`.

The independent verifier command passed for the mounted volume, runtime root, logs, and DB. The verifier does not trust runtime self-report and derives real paths/device IDs itself.

`INDEPENDENT_EXTERNAL_STORAGE_VERIFIER_PASS=true` for the verified current authority; full V33B readiness still depends on the remaining physical fault controls.
