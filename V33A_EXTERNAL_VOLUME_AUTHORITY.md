# V33A external-volume authority

Candidate: `f44e637f4fea04dd824f47cf4a0202840be3ff1d`
Validated source: `/Volumes/TradeBotData/tradebot-live-candidate-f44e637`
Successor: `/Volumes/TradeBotData/tradebot-live-diskguard-successor-20260905`

## Observed authority

- Expected volume: `/Volumes/TradeBotData`
- `realpath`: `/Volumes/TradeBotData`
- Device ID: `16777240`
- Filesystem: `apfs`
- Mount: `/dev/disk5s1 on /Volumes/TradeBotData (apfs, local, nodev, nosuid, journaled, noowners)`
- Writable probe: PASS
- Same-device temporary-file probe: PASS (`16777240`)
- Successor and runtime root device: `16777240`

This proves the mounted external volume is present, writable, and the validated successor's default runtime root is on it. It does not prove that every historical or optional writer is externally bound.

## Boundary

The live observer must be launched with an explicit runtime root under the mounted volume and explicit paths for any compatibility mirrors. A default `repo_logs_dir()` path under the source checkout is an internal-disk spill risk and is not accepted as live evidence authority.

Result: `EXTERNAL_VOLUME_PRESENT_AND_DEVICE_BOUND=true`; `ALL_MATERIAL_LIVE_WRITERS_EXTERNAL=false` pending closure of compatibility-mirror paths.
