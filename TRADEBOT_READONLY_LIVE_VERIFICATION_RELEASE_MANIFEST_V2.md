# Read-only live-verification release manifest V2

Candidate SHA: `73eb9e1d5b964de52924faa26e2fafb36d5d946a`

Manifest JSON SHA256: `21586f446eb61bfeb53560c0500ce3d9d9a44a2b8d9dc36a7077eeb3b948ed3c`
Prospective manifest SHA256: `5e4cbc7761aae6d4145ce9e7761f3d4ec292b1a67160910dc1822d81f75e60f`
CAS primitive specification SHA256: `55bc42abb8574f686c20175e7adf43e43835c03b990978bc68767862408f0c59`
Canonical launcher SHA256: `8edd03cc13e74f6b1d1dbe01560136ee97e662ac61e26305051f27a8325fdd8b`
Validation coverage: prospective `118/118`; A-X `47/47`; scenarios `24/24`.

The JSON companion is authoritative for machine comparison. The release image
is the exact-SHA source package. The canonical launcher is the V1 Kite
read-only observer listed in `V38_CANONICAL_LAUNCHER_AUTHORITY.md`.

Primary runtime/evidence storage is `/Volumes/TradeBotData`; internal storage
is reserved for governed source survivability and emergency policy only.
Future evidence roots must use the V38 root contract. No live authorization is
granted by this manifest.
