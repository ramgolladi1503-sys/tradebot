"""Governed morning launcher orchestrator.

Implements deterministic state machine:
START -> VERIFY_RELEASE -> VERIFY_STORAGE -> CHECK_AUTH ->
[AUTH_VALID | (WAITING_HUMAN_AUTH -> DETECT_FRESH_TOKEN -> VALIDATE_AUTH -> AUTH_VALID)] ->
REFRESH_INSTRUMENTS_IF_REQUIRED -> CONNECT_WEBSOCKET -> VERIFY_MARKET_DATA ->
ARM_OBSERVER -> OBSERVER_RUNNING (or STOPPED / BLOCKED).

Strict safety:
- broker_write_authority = false
- order_authority = false
- paper_authorized = false
- live_authorized = false
- Never store passwords, PIN, TOTP seed, or credentials in Git/evidence.
- No second manual command required after human login.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
IST_TZ = ZoneInfo("Asia/Kolkata")


class LauncherState(str, Enum):
    START = "START"
    VERIFY_RELEASE = "VERIFY_RELEASE"
    VERIFY_STORAGE = "VERIFY_STORAGE"
    CHECK_AUTH = "CHECK_AUTH"
    AUTH_VALID = "AUTH_VALID"
    WAITING_HUMAN_AUTH = "WAITING_HUMAN_AUTH"
    DETECT_FRESH_TOKEN = "DETECT_FRESH_TOKEN"
    VALIDATE_AUTH = "VALIDATE_AUTH"
    REFRESH_INSTRUMENTS_IF_REQUIRED = "REFRESH_INSTRUMENTS_IF_REQUIRED"
    CONNECT_WEBSOCKET = "CONNECT_WEBSOCKET"
    VERIFY_MARKET_DATA = "VERIFY_MARKET_DATA"
    ARM_OBSERVER = "ARM_OBSERVER"
    OBSERVER_RUNNING = "OBSERVER_RUNNING"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"


@dataclass
class TokenFileSnapshot:
    exists: bool
    size: int
    mtime: float
    digest: str


def snapshot_token_file(path: Path) -> TokenFileSnapshot:
    """Capture token file metadata without logging or exposing secret value."""
    if not path.is_file():
        return TokenFileSnapshot(exists=False, size=0, mtime=0.0, digest="")
    try:
        st = path.stat()
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        return TokenFileSnapshot(exists=True, size=st.st_size, mtime=st.st_mtime, digest=digest)
    except OSError:
        return TokenFileSnapshot(exists=False, size=0, mtime=0.0, digest="")


class GovernedMorningOrchestrator:
    def __init__(
        self,
        *,
        repo_root: Path,
        state_root: Path,
        session_date: str | None = None,
        token_path: Path | None = None,
        auth_timeout_seconds: float = 600.0,
        expected_release_sha: str | None = None,
        storage_volume: Path = Path("/Volumes/TradeBotData"),
        lock_file: Path | None = None,
        open_browser: bool = True,
        dry_run: bool = False,
        telemetry_callback: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.session_date = session_date or datetime.now(IST_TZ).date().isoformat()
        self.token_path = Path(token_path).resolve() if token_path else (self.repo_root / ".runtime" / "kite_access_token")
        self.auth_timeout_seconds = float(auth_timeout_seconds)
        self.expected_release_sha = expected_release_sha
        self.storage_volume = Path(storage_volume).resolve()
        self.lock_file = Path(lock_file).resolve() if lock_file else (self.repo_root / ".runtime" / ".governed_morning_launcher.lock")
        self.open_browser = open_browser
        self.dry_run = dry_run
        self.telemetry_callback = telemetry_callback

        self.state = LauncherState.START
        self.state_history: list[dict[str, Any]] = []
        self.blocker_reason: str | None = None
        self.stop_reason: str | None = None

        self._initial_token_snapshot: TokenFileSnapshot | None = None
        self._lock_acquired = False
        self._child_observer_proc: subprocess.Popen | None = None
        self._ws_client: Any = None
        self.ws_connected = False
        self.instrument_universe_count = 0
        self.ws_tokens: list[int] = []
        self.broker_user_id: str | None = None

    def emit(self, step_name: str, status: str, detail: str = "") -> None:
        ts = datetime.now(IST_TZ).strftime("%H:%M:%S")
        line = f"[{ts}] {step_name:<14} {status:<18} {detail}".strip()
        print(line, flush=True)
        if self.telemetry_callback:
            self.telemetry_callback(step_name, status, detail)

    def transition(self, new_state: LauncherState, reason: str | None = None) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = {
            "from_state": self.state.value,
            "to_state": new_state.value,
            "reason": reason,
            "timestamp": now_iso,
        }
        self.state_history.append(entry)
        self.state = new_state
        if new_state == LauncherState.BLOCKED:
            self.blocker_reason = reason
        elif new_state == LauncherState.STOPPED:
            self.stop_reason = reason

    def acquire_lock(self) -> bool:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_file.exists():
            try:
                data = json.loads(self.lock_file.read_text(encoding="utf-8"))
                pid = int(data.get("pid", 0))
                if pid > 0:
                    try:
                        os.kill(pid, 0)
                        self.emit("LOCK", "BLOCKED", f"Active launcher running with PID {pid}")
                        return False
                    except OSError:
                        # Process dead, stale lock can be reclaimed safely
                        pass
            except (json.JSONDecodeError, OSError, ValueError):
                pass

        payload = {
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "session_date": self.session_date,
        }
        self.lock_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self._lock_acquired = True
        return True

    def release_lock(self) -> None:
        if self._lock_acquired and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except OSError:
                pass
            self._lock_acquired = False

    def step_verify_release(self) -> bool:
        self.emit("RELEASE", "CHECKING")
        try:
            head_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(self.repo_root), text=True
            ).strip()
            dirty = subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=str(self.repo_root), text=True
            ).strip()
        except subprocess.SubprocessError as exc:
            self.emit("RELEASE", "FAIL", f"Git inspection failed: {exc}")
            self.transition(LauncherState.BLOCKED, f"git_error:{exc}")
            return False

        if dirty:
            self.emit("RELEASE", "FAIL", "Worktree is dirty")
            self.transition(LauncherState.BLOCKED, "worktree_dirty")
            return False

        if self.expected_release_sha and head_sha != self.expected_release_sha:
            self.emit("RELEASE", "FAIL", f"SHA mismatch expected {self.expected_release_sha[:8]} != {head_sha[:8]}")
            self.transition(LauncherState.BLOCKED, "release_sha_mismatch")
            return False

        self.emit("RELEASE", "PASS", f"SHA {head_sha[:8]}")
        self.transition(LauncherState.VERIFY_STORAGE)
        return True

    def step_verify_storage(self) -> bool:
        self.emit("STORAGE", "CHECKING")
        from core.runtime_storage_authority import StorageAuthorityError, establish, bind_environment
        try:
            runtime_output = self.state_root / "sessions" / f"session_{self.session_date}"
            auth = establish(volume=self.storage_volume, runtime_root=runtime_output)
            bind_environment(auth)
        except StorageAuthorityError as exc:
            self.emit("STORAGE", "FAIL", str(exc))
            self.transition(LauncherState.BLOCKED, str(exc))
            return False

        # SQLite integrity check
        from core.paths import db_dir
        db_file = db_dir() / "DEFAULT.sqlite"
        if db_file.exists():
            import sqlite3
            try:
                with sqlite3.connect(str(db_file)) as conn:
                    res = conn.execute("PRAGMA integrity_check;").fetchall()
                    if res != [("ok",)]:
                        self.emit("STORAGE", "FAIL", f"Corrupt SQLite DB: {res}")
                        self.transition(LauncherState.BLOCKED, "corrupt_sqlite_db")
                        return False
            except Exception as exc:
                self.emit("STORAGE", "FAIL", f"SQLite error: {exc}")
                self.transition(LauncherState.BLOCKED, f"sqlite_error:{exc}")
                return False

        self.emit("STORAGE", "PASS", f"Volume {self.storage_volume.name} ok")
        self.transition(LauncherState.CHECK_AUTH)
        return True

    def validate_broker_read(self) -> tuple[bool, str | None, str | None]:
        """Perform a strictly read-only broker profile call. Never calls write endpoints."""
        from core.auth import get_kite_client
        try:
            client = get_kite_client(repo_root_path=self.repo_root)
            prof = client.profile()
            uid = str(prof.get("user_id") or "").strip()
            if not uid:
                return False, None, "missing_user_id"
            return True, uid, None
        except Exception as exc:
            return False, None, f"{type(exc).__name__}:{exc}"

    def step_check_auth(self) -> bool:
        self.emit("AUTH", "CHECKING")
        self._initial_token_snapshot = snapshot_token_file(self.token_path)

        if not self._initial_token_snapshot.exists or self._initial_token_snapshot.size == 0:
            self.emit("AUTH", "MISSING", "No access token file found")
            self.transition(LauncherState.WAITING_HUMAN_AUTH, "token_file_missing")
            return False

        ok, uid, err = self.validate_broker_read()
        if ok and uid:
            self.broker_user_id = uid
            self.emit("AUTH", "PASS", f"User {uid[-4:] if len(uid) >= 4 else uid} valid")
            self.transition(LauncherState.AUTH_VALID)
            return True

        self.emit("AUTH", "EXPIRED", f"Broker validation failed: {err}")
        self.transition(LauncherState.WAITING_HUMAN_AUTH, "token_expired_or_invalid")
        return False

    def get_login_url(self) -> str | None:
        try:
            from core.kite_client import kite_client
            from scripts.kite_autologin_localhost import _resolve_api_key
            api_key = _resolve_api_key()
            return kite_client.login_url(api_key=api_key)
        except Exception:
            return None

    def step_wait_human_auth(self, *, poll_interval: float = 0.5, timeout_override: float | None = None) -> bool:
        timeout = timeout_override if timeout_override is not None else self.auth_timeout_seconds
        self.emit("AUTH", "WAITING_HUMAN_AUTH", f"Timeout {int(timeout)}s")

        login_url = self.get_login_url()
        if login_url:
            print(f"\n[ACTION REQUIRED] Please log in to Zerodha/Kite in browser:\n{login_url}\n", flush=True)
            if self.open_browser:
                try:
                    import webbrowser
                    webbrowser.open(login_url)
                except Exception:
                    pass

        deadline = time.time() + timeout
        initial_snap = self._initial_token_snapshot or snapshot_token_file(self.token_path)

        while time.time() < deadline:
            current_snap = snapshot_token_file(self.token_path)
            # Detect creation or modification
            if current_snap.exists and current_snap.size > 0:
                if not initial_snap.exists:
                    self.emit("AUTH", "TOKEN_DETECTED", "New token file created")
                    self.transition(LauncherState.DETECT_FRESH_TOKEN, "new_token_file_detected")
                    return True
                if current_snap.mtime > initial_snap.mtime or current_snap.digest != initial_snap.digest:
                    self.emit("AUTH", "TOKEN_DETECTED", "Token file modified")
                    self.transition(LauncherState.DETECT_FRESH_TOKEN, "token_file_updated")
                    return True
            time.sleep(poll_interval)

        self.emit("AUTH", "TIMEOUT", f"Human authentication timed out after {int(timeout)}s")
        self.transition(LauncherState.STOPPED, "auth_timeout_waiting_human_auth")
        return False

    def step_validate_auth(self, max_retries: int = 3) -> bool:
        self.transition(LauncherState.VALIDATE_AUTH)
        self.emit("AUTH", "VALIDATING")
        for attempt in range(1, max_retries + 1):
            ok, uid, err = self.validate_broker_read()
            if ok and uid:
                self.broker_user_id = uid
                self.emit("AUTH", "PASS", f"User {uid[-4:] if len(uid) >= 4 else uid} validated")
                self.transition(LauncherState.AUTH_VALID)
                return True
            time.sleep(0.5)

        self.emit("AUTH", "INVALID", f"Broker rejected token: {err}")
        self.transition(LauncherState.WAITING_HUMAN_AUTH, "changed_token_validation_failed")
        return False

    def step_refresh_instruments(self) -> bool:
        self.emit("INSTRUMENTS", "CHECKING")
        from core.auth import get_kite_client
        from core.read_only_instrument_authority import fetch_current_instruments
        from core.daily_instrument_authority import independent_verify
        from core.instruments import build_option_registry, select_expiry

        try:
            client = get_kite_client(repo_root_path=self.repo_root)
            rows = fetch_current_instruments(client, exchanges=("NSE", "NFO", "BFO"))
        except Exception as exc:
            self.emit("INSTRUMENTS", "FAIL", f"Failed fetching instruments: {exc}")
            self.transition(LauncherState.BLOCKED, f"instrument_fetch_failed:{exc}")
            return False

        v_res = independent_verify(rows, [256265, 260105], index_token=256265)
        if v_res["status"] != "PASS":
            self.emit("INSTRUMENTS", "FAIL", f"Verification failed: {v_res}")
            self.transition(LauncherState.BLOCKED, "instrument_verification_failed")
            return False

        # Derive option contracts and WS universe
        index_tokens = [256265, 260105, 265]
        opt_tokens: set[int] = set()
        for sym in ["NIFTY", "BANKNIFTY", "SENSEX"]:
            reg = build_option_registry(symbol=sym, instruments=rows)
            nearest_exp = select_expiry(reg["available_expiries"])
            for inst in reg["instruments"]:
                if inst.get("expiry") == nearest_exp and inst.get("instrument_token"):
                    opt_tokens.add(int(inst["instrument_token"]))

        self.ws_tokens = sorted(set(index_tokens + list(opt_tokens)))
        self.instrument_universe_count = len(rows)
        self.emit("INSTRUMENTS", "PASS", f"{len(rows)} parsed, {len(self.ws_tokens)} subscription tokens")
        self.transition(LauncherState.CONNECT_WEBSOCKET)
        return True

    def step_connect_websocket(self) -> bool:
        self.emit("WEBSOCKET", "CONNECTING")
        from kiteconnect import KiteTicker
        from core.auth import get_kite_credentials

        try:
            api_key, access_token = get_kite_credentials(repo_root_path=self.repo_root)
            self._ws_client = KiteTicker(api_key, access_token)
        except Exception as exc:
            self.emit("WEBSOCKET", "FAIL", f"Ticker init failed: {exc}")
            self.transition(LauncherState.BLOCKED, f"websocket_init_failed:{exc}")
            return False

        connected = False
        def on_connect(ws, resp):
            nonlocal connected
            connected = True

        self._ws_client.on_connect = on_connect
        try:
            import threading
            th = threading.Thread(target=self._ws_client.connect, kwargs={"threaded": True}, daemon=True)
            th.start()
            time.sleep(1.5)
        except Exception as exc:
            self.emit("WEBSOCKET", "FAIL", f"Connection error: {exc}")
            self.transition(LauncherState.BLOCKED, f"websocket_connect_failed:{exc}")
            return False

        self.ws_connected = connected
        if connected:
            self.emit("WEBSOCKET", "CONNECTED")
        else:
            self.emit("WEBSOCKET", "INITIALIZED", "Handshake pending/off-hours")

        self.transition(LauncherState.VERIFY_MARKET_DATA)
        return True

    def step_verify_market_data(self) -> bool:
        self.emit("MARKET_DATA", "EVALUATING")
        now_time = datetime.now(IST_TZ).time()
        market_open = (
            datetime.strptime("09:15", "%H:%M").time()
            <= now_time
            <= datetime.strptime("15:30", "%H:%M").time()
        )
        if market_open and self.ws_connected:
            self.emit("MARKET_DATA", "ACTIVE")
        else:
            self.emit("MARKET_DATA", "WAITING_FOR_BROADCAST", "Market closed or pre-open window")

        self.transition(LauncherState.ARM_OBSERVER)
        return True

    def step_arm_observer(self) -> bool:
        self.emit("OBSERVER", "ARMING")
        if self.dry_run:
            self.emit("OBSERVER", "ARMED", "Dry-run mode; observer not spawned")
            self.transition(LauncherState.STOPPED, "dry_run_complete")
            return True

        # Check pre-open / market timing
        now_time = datetime.now(IST_TZ).time()
        can_launch_live = (
            datetime.strptime("08:55", "%H:%M").time()
            <= now_time
            <= datetime.strptime("15:30", "%H:%M").time()
        )
        if not can_launch_live:
            self.emit("OBSERVER", "STANDBY", f"Current time {now_time.strftime('%H:%M')} outside active window 08:55-15:30 IST")
            self.transition(LauncherState.STOPPED, "outside_session_timing_window")
            return True

        self.emit("OBSERVER", "LAUNCHING", "Starting read-only observer")
        cmd = [
            sys.executable,
            str(self.repo_root / "scripts" / "run_kite_read_only_observation_v1.py"),
            "--session-date", self.session_date,
            "--output-root", str(self.state_root / "sessions" / f"session_{self.session_date}"),
            "--token-path", str(self.token_path),
            "--validate-only",
        ]
        try:
            self._child_observer_proc = subprocess.Popen(cmd, cwd=str(self.repo_root))
            self.emit("OBSERVER", "RUNNING", f"Child PID {self._child_observer_proc.pid}")
            self.transition(LauncherState.OBSERVER_RUNNING)
            return True
        except Exception as exc:
            self.emit("OBSERVER", "FAIL", f"Launch failed: {exc}")
            self.transition(LauncherState.BLOCKED, f"observer_launch_failed:{exc}")
            return False

    def stop(self, reason: str = "operator_shutdown") -> None:
        if self._child_observer_proc and self._child_observer_proc.poll() is None:
            try:
                self._child_observer_proc.terminate()
                self._child_observer_proc.wait(timeout=3.0)
            except Exception:
                try:
                    self._child_observer_proc.kill()
                except Exception:
                    pass

        if self._ws_client:
            try:
                self._ws_client.close()
            except Exception:
                pass

        self.release_lock()
        self.transition(LauncherState.STOPPED, reason)
        self.emit("ORCHESTRATOR", "STOPPED", reason)

    def run(self) -> LauncherState:
        """Run the full deterministic state machine."""
        if not self.acquire_lock():
            self.transition(LauncherState.BLOCKED, "GOVERNED_MORNING_LAUNCHER_ALREADY_RUNNING")
            return self.state

        try:
            # 1. VERIFY_RELEASE
            if not self.step_verify_release():
                if self.state not in {LauncherState.BLOCKED, LauncherState.STOPPED}:
                    self.transition(LauncherState.BLOCKED, "release_verification_failed")
                return self.state

            # 2. VERIFY_STORAGE
            if not self.step_verify_storage():
                if self.state not in {LauncherState.BLOCKED, LauncherState.STOPPED}:
                    self.transition(LauncherState.BLOCKED, "storage_verification_failed")
                return self.state

            # 3. CHECK_AUTH
            auth_ok = self.step_check_auth()
            if not auth_ok:
                # 4. WAITING_HUMAN_AUTH -> DETECT_FRESH_TOKEN
                if not self.step_wait_human_auth():
                    if self.state not in {LauncherState.BLOCKED, LauncherState.STOPPED}:
                        self.transition(LauncherState.STOPPED, "auth_timeout_or_stopped")
                    return self.state
                # 5. VALIDATE_AUTH -> AUTH_VALID
                if not self.step_validate_auth():
                    return self.state

            # 6. REFRESH_INSTRUMENTS_IF_REQUIRED
            self.transition(LauncherState.REFRESH_INSTRUMENTS_IF_REQUIRED)
            if not self.step_refresh_instruments():
                return self.state

            # 7. CONNECT_WEBSOCKET
            self.transition(LauncherState.CONNECT_WEBSOCKET)
            if not self.step_connect_websocket():
                return self.state

            # 8. VERIFY_MARKET_DATA
            self.transition(LauncherState.VERIFY_MARKET_DATA)
            if not self.step_verify_market_data():
                return self.state

            # 9. ARM_OBSERVER
            self.transition(LauncherState.ARM_OBSERVER)
            self.step_arm_observer()
            return self.state

        finally:
            if self.state not in {LauncherState.OBSERVER_RUNNING}:
                self.release_lock()
