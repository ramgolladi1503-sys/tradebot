# Read-only live-verification authorization packet V2

Authorization packet JSON SHA256: `b9558af99b947b49be2bc008c39b035eda99ae6f14c58a09c7eacc3dea92d40b`
Authorization state: `NOT_AUTHORIZED`

This packet is a preflight contract, not authorization to start a session.
Every gate fails closed. Startup order is: candidate SHA, internal release,
external storage, emergency storage, disk reserve, contract hashes,
credential authority, same-day instruments, read-only broker auth, feed,
subscriptions, persistence, canonical cycle, CAS arming, then prospective
observation.

Live-only gates remain unverified until a separately authorized future session:
same-day authentication/instruments, feed/depth/option freshness, connect and
recovery behavior, and close sealing. Broker-write and order authority remain
false throughout.
