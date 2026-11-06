# Aixion TradeBot Pocket — Repository and Runtime Discovery

**Date**: 2026-11-06  
**Environment**: macOS (Apple M1 Pro, Darwin arm64)  
**Host Architecture**: Local MacBook Pro  

---

## 1. Verified Repositories, Paths, and Isolated Worktree
- **Primary Repository**: `/Users/madhuram/tradebot`
- **Current Base Commit**: `fcde21c74` (`feat(sentinel): implement dynamic per-index gear tracking, priority arbiter, and dual-stream shadow tagging`)
- **Isolated Worktree & Branch**: `/Users/madhuram/tradebot-pocket-companion` on branch `feat/tradebot-pocket-companion`
- **Safety Precaution**: Preserves existing `main` and active branches untouched.

---

## 2. Real Market Feed, Broker Adapters & Authority Ownership
- **Broker Adapter**: Upstox V2 API (`core/upstox_market_feed.py`, `core/broker_upstox.py`, `core/upstox_profile.py`).
- **Token Location**: `runtime/upstox_token.txt` (or `.env` configuration `UPSTOX_ACCESS_TOKEN`).
- **Market Stream**: Real-time WebSocket connection to Upstox market data feed; maintains depth, OHLC, VWAP, LTP, and Greeks.
- **Audit Logging**: `runtime/audit/sentinel_execution_paths_YYYY-MM-DD.jsonl` provides continuous execution telemetry and signals.

---

## 3. Source of Truth Map
1. **Active Positions & Executions**:
   - Primary: `runtime/sentinel_apm_wal.json` (NIFTY APM WAL)
   - Multi-Index: `runtime/sentinel_apm_wal_sensex.json`, `runtime/sentinel_apm_wal_banknifty.json`
   - Trade history, entry price, trailing stops, quantity, P&L, and in-flight order states are logged immutably.
2. **Support/Resistance & Options Walls**:
   - `runtime/sentinel_wall_state_nifty.json`
   - `runtime/sentinel_wall_state_sensex.json`
   - `runtime/sentinel_wall_state_banknifty.json`
3. **Execution Telemetry & Signals**:
   - `runtime/audit/sentinel_execution_paths_<YYYY-MM-DD>.jsonl`
4. **Broker Authentication & Health**:
   - Token check on `runtime/upstox_token.txt` (mtime & validity via profile API)
   - Daily login script: `scripts/login_upstox.py` / `scripts/run_daily_upstox_pipeline.sh`.

---

## 4. Mac Companion Service Architecture
- **Framework**: FastAPI + Uvicorn (available in Python environment `/opt/anaconda3/bin/python3`).
- **Mode**: Strictly **READ-ONLY** (`read_only = True`, `is_order_action = False`, `broker_api_called = False`, `allowed_for_live_execution = False`).
- **No Remote Order Actions**: No POST endpoints for order entry, cancellation, or risk parameter overrides.
- **Security & Network**:
  - Bound to `127.0.0.1:8765` or Tailscale interface IP.
  - Authenticated via preshared bearer token (`X-Aixion-Pocket-Key`).
  - Tailscale Serve will proxy secure HTTPS traffic over tailnet only (`tailscale serve https / http://127.0.0.1:8765`).

---

## 5. Mobile App Toolchain & Android Environment
- **JDK**: Eclipse Adoptium OpenJDK 17 (`/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home`).
- **Android SDK**: `/Users/madhuram/Library/Android/sdk`
  - Platforms: `android-35`
  - Build Tools: `35.0.0`, `34.0.0`
  - Cmdline Tools: `latest` (`23.0.0`)
  - Emulator: `37.2.12` with system image `android-35/google_apis/arm64-v8a`
- **Gradle**: Will provision using Gradle Wrapper (`gradle-8.9-bin.zip` or `gradle-8.7-bin.zip`).
- **Architecture**: Kotlin + Jetpack Compose + Material 3 + Retrofit/OkHttp + KotlinX Coroutines & Serialization.
