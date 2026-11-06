# Aixion TradeBot Pocket — Complete System, Verification & Setup Guide

**Application**: Aixion TradeBot Pocket (Native Android Kotlin/Compose)  
**Host Architecture**: Mac Companion Read-Only API + Private Tailscale Network  
**Security Model**: Strictly Read-Only • Zero Order Endpoints • No Cloud Costs  

---

## 1. Verified Deliverables & Artifacts

### 1.1 Android Native Application (APK)
- **APK Path**: `/Users/madhuram/tradebot-pocket-companion/android/app/build/outputs/apk/debug/app-debug.apk`
- **Package Name**: `com.aixion.tradebotpocket`
- **Min SDK**: 26 (Android 8.0 Oreo) • **Target SDK**: 35 (Android 15)
- **SHA256 Checksum**:
  ```text
  45feb91bc6fce7e8f2ff0c065a10110d66e59212feda708185426be743d8abbe
  ```

### 1.2 Mac Companion Service
- **Source**: `/Users/madhuram/tradebot-pocket-companion/pocket_companion/service.py`
- **Test Suite**: `/Users/madhuram/tradebot-pocket-companion/tests/pocket_companion/test_service.py`
- **Service Verification**: 100% passing tests (`pytest tests/pocket_companion/`).
- **Core Endpoints**:
  - `GET /health`: Mac awake status, broker token validity (`VALID`, `STALE`, `EXPIRED`), feed freshness (`ACTIVE_LIVE`, `IDLE_POST_MARKET`, `STALE`), server time.
  - `GET /positions`: Authoritative APM WAL multi-index positions (NIFTY, SENSEX, BANKNIFTY), real-time unrealized P&L, today's total realized P&L, completed trade history.
  - `GET /market`: Option walls, major Call/Put walls, index support/resistance levels.
  - `GET /signals`: Immutable audit trail of Sentinel execution path events.

---

## 2. Invariant & Safety Proofs
All mobile endpoints enforce:
```python
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
```
- **Zero Order Mutation Routes**: POST, PUT, DELETE requests to `/order`, `/orders`, `/trade` return 404/405.
- **Credential Protection**: Broker access tokens, API secrets, and order signing keys are strictly confined to the local Mac and never transmitted to or stored on the mobile device.

---

## 3. End-to-End Installation & Tailscale Connection Instructions

### Step 1: Install APK on Android Device
Connect your Android phone via USB (or transfer the APK via Google Drive / local file transfer):
```bash
adb install -r /Users/madhuram/tradebot-pocket-companion/android/app/build/outputs/apk/debug/app-debug.apk
```

### Step 2: Start Companion Service on Mac
Run the companion daemon locally:
```bash
cd /Users/madhuram/tradebot-pocket-companion
/opt/anaconda3/bin/python3 -m uvicorn pocket_companion.service:app --host 127.0.0.1 --port 8765
```

### Step 3: Configure Private Tailscale Access
1. Install Tailscale on your Mac (`brew install --cask tailscale` or App Store) and Android phone via Google Play Store.
2. Sign in to the same Tailscale account (tailnet) on both devices.
3. Expose the companion API privately over Tailscale Serve on the Mac:
   ```bash
   tailscale serve --bg http://127.0.0.1:8765
   ```
4. Find your Mac's Tailscale IP or MagicDNS name (e.g., `http://mymac.tailscale.net:8765` or `http://100.x.y.z:8765`).

### Step 4: Connect from the Android App
1. Open **Aixion TradeBot Pocket** on your Android phone.
2. Tap **HOST** in the top-right app bar.
3. Enter your Mac's Tailscale endpoint (e.g., `http://100.x.y.z:8765`) and preshared key (`aixion-pocket-secret-key-v1`).
4. Tap **Save & Connect**.
