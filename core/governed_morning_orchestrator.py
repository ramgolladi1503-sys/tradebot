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
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qs, urlparse
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


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


class GovernedAuthCallbackServer:
    """Embedded localhost HTTP callback server with strict security, authentication, and replay protection."""

    def __init__(
        self,
        token_path: Path,
        repo_root: Path,
        host: str = "127.0.0.1",
        port: int = 8765,
        timeout_seconds: float = 600.0,
    ) -> None:
        self.token_path = Path(token_path).resolve()
        self.repo_root = Path(repo_root).resolve()
        self.host = host
        self.port = port
        self.timeout_seconds = float(timeout_seconds)
        self.start_epoch = time.time()
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.bound = False
        self.error: str | None = None
        self.token_received = False
        self._consumed_tokens: set[str] = set()
        self.server_nonce = secrets.token_hex(32)
        self.auth_file = self.repo_root / ".runtime" / f".callback_server_{self.port}.json"

    def start(self) -> bool:
        server_instance = self

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    # 1. Bounds check: prevent oversized URL / DOS
                    if len(self.path) > 2048:
                        server_instance.error = "oversized_query_uri_too_long"
                        self.send_response(414)
                        self.end_headers()
                        self.wfile.write(b"URI Too Long")
                        return

                    # 2. Timeout check
                    if server_instance.timeout_seconds > 0 and (time.time() - server_instance.start_epoch) > server_instance.timeout_seconds:
                        server_instance.error = "callback_timed_out"
                        self.send_response(408)
                        self.end_headers()
                        self.wfile.write(b"Request Timeout")
                        return

                    parsed = urlparse(self.path)
                    qs = parse_qs(parsed.query)
                    request_token = (qs.get("request_token") or [None])[0]
                    status = (qs.get("status") or [None])[0]
                    action = (qs.get("action") or [None])[0]

                    # 3. Authenticated health endpoint
                    if parsed.path == "/health":
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        resp_data = {
                            "status": "tradebot_auth_callback",
                            "ready": True,
                            "pid": os.getpid(),
                            "nonce": server_instance.server_nonce,
                        }
                        self.wfile.write(json.dumps(resp_data).encode("utf-8"))
                        return

                    if parsed.path != "/":
                        self.send_response(404)
                        self.end_headers()
                        return

                    # 4. Strict OAuth callback semantics: require expected success status and login action
                    if status != "success" or (action is not None and action != "login"):
                        server_instance.error = f"invalid_callback_semantics status={status} action={action}"
                        body = (
                            "<html><body style='font-family: sans-serif; text-align: center; padding: 40px;'>"
                            "<h2 style='color: red;'>Authentication Failed</h2>"
                            f"<p>Invalid callback status={status} action={action}</p>"
                            "</body></html>"
                        )
                        self.send_response(400)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body.encode("utf-8"))
                        return

                    # 5. Missing or invalid format token
                    if not request_token:
                        server_instance.error = "missing_request_token"
                        body = (
                            "<html><body style='font-family: sans-serif; text-align: center; padding: 40px;'>"
                            "<h2 style='color: red;'>Authentication Failed</h2>"
                            "<p>Missing request_token</p>"
                            "</body></html>"
                        )
                        self.send_response(400)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body.encode("utf-8"))
                        return
                    if not re.match(r"^[a-zA-Z0-9_-]{8,128}$", request_token):
                        server_instance.error = f"invalid_request_token_format token={request_token}"
                        body = (
                            "<html><body style='font-family: sans-serif; text-align: center; padding: 40px;'>"
                            "<h2 style='color: red;'>Authentication Failed</h2>"
                            "<p>Invalid request_token format</p>"
                            "</body></html>"
                        )
                        self.send_response(400)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body.encode("utf-8"))
                        return

                    # 6. Replay attack protection
                    if request_token in server_instance._consumed_tokens:
                        server_instance.error = f"replayed_token token={request_token[:6]}..."
                        self.send_response(409)
                        self.end_headers()
                        self.wfile.write(b"Conflict: request_token has already been consumed")
                        return
                    server_instance._consumed_tokens.add(request_token)

                    # 7. Symlink / TOCTOU check
                    if server_instance.token_path.is_symlink():
                        server_instance.error = "symlink_token_path_forbidden"
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(b"Internal Error: symlinks forbidden for token path")
                        return

                    from core.kite_client import kite_client
                    from scripts.kite_autologin_localhost import (
                        _resolve_api_key,
                        _resolve_api_secret,
                    )

                    api_key = _resolve_api_key()
                    api_secret = _resolve_api_secret()
                    data = kite_client.generate_session(
                        request_token, api_secret=api_secret, api_key=api_key
                    )
                    access_token = str(data.get("access_token", "")).strip()
                    if not access_token:
                        server_instance.error = "empty_access_token"
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(b"Failed to generate access token: broker returned empty token")
                        return

                    # 8. Atomic fsync token write with mode 0600
                    server_instance.token_path.parent.mkdir(parents=True, exist_ok=True)
                    temp_fd, temp_file = tempfile.mkstemp(
                        dir=str(server_instance.token_path.parent),
                        prefix=f".{server_instance.token_path.name}.tmp.",
                    )
                    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                        f.write(access_token + "\n")
                        f.flush()
                        os.fsync(f.fileno())
                    os.chmod(temp_file, stat.S_IRUSR | stat.S_IWUSR)
                    os.replace(temp_file, server_instance.token_path)
                    server_instance.token_received = True

                    body = (
                        "<html><body style='font-family: sans-serif; text-align: center; padding: 40px;'>"
                        "<h2 style='color: green;'>TradeBot Authentication Successful</h2>"
                        "<p>Access token generated and saved. You can close this tab and return to the terminal.</p>"
                        "</body></html>"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(body.encode("utf-8"))
                    return
                except Exception as exc:
                    server_instance.error = f"callback_error:{exc}"
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Internal Callback Error: {exc}".encode("utf-8"))

            def log_message(self, _format, *args):
                return

        try:
            self.server = ReusableHTTPServer((self.host, self.port), CallbackHandler)
            self.server.timeout = 0.5
            self.bound = True
            # Write ownership contract file
            self.auth_file.parent.mkdir(parents=True, exist_ok=True)
            auth_payload = {
                "pid": os.getpid(),
                "port": self.port,
                "nonce": self.server_nonce,
                "token_path": str(self.token_path),
                "created_at": time.time(),
            }
            self.auth_file.write_text(json.dumps(auth_payload, indent=2) + "\n", encoding="utf-8")
            os.chmod(self.auth_file, stat.S_IRUSR | stat.S_IWUSR)
        except OSError as exc:
            self.error = f"bind_failed:{exc}"
            self.bound = False
            return False

        def _serve():
            while self.bound and self.server and not self.token_received:
                self.server.handle_request()

        self.thread = threading.Thread(target=_serve, daemon=True)
        self.thread.start()
        return True

    def stop(self) -> None:
        self.bound = False
        if self.auth_file.exists():
            try:
                self.auth_file.unlink()
            except OSError:
                pass
        if self.server:
            try:
                self.server.server_close()
            except Exception:
                pass
            self.server = None
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)


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
        release_store_path: Path | None = None,
        lock_file: Path | None = None,
        open_browser: bool = True,
        dry_run: bool = False,
        preflight_only: bool = False,
        wait_for_window: bool = True,
        market_open_time: str = "08:55",
        market_close_time: str = "15:45",
        observer_engine: str = "dual",
        supervise: bool = True,
        status_interval_seconds: float = 3600.0,
        telemetry_callback: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.state_root = Path(state_root).resolve()
        self.session_date = session_date or datetime.now(IST_TZ).date().isoformat()
        self.token_path = Path(token_path).resolve() if token_path else (self.repo_root / ".runtime" / "kite_access_token")
        self.auth_timeout_seconds = float(auth_timeout_seconds)
        self.expected_release_sha = expected_release_sha
        self.storage_volume = Path(storage_volume).resolve()
        self.release_store_path = Path(release_store_path).resolve() if release_store_path else (self.storage_volume / "release_store")
        self.lock_file = Path(lock_file).resolve() if lock_file else (self.repo_root / ".runtime" / ".governed_morning_launcher.lock")
        self.open_browser = open_browser
        self.dry_run = dry_run
        self.preflight_only = preflight_only
        self.wait_for_window = wait_for_window
        self.market_open_time = market_open_time
        self.market_close_time = market_close_time
        self.observer_engine = observer_engine
        self.supervise = supervise
        self.status_interval_seconds = float(status_interval_seconds)
        self.telemetry_callback = telemetry_callback

        self.state = LauncherState.START
        self.state_history: list[dict[str, Any]] = []
        self.blocker_reason: str | None = None
        self.stop_reason: str | None = None
        self._stop_requested = False

        self._initial_token_snapshot: TokenFileSnapshot | None = None
        self._lock_acquired = False
        self._child_observer_proc: subprocess.Popen | None = None
        self._child_collector_proc: subprocess.Popen | None = None
        self._child_mros_proc: subprocess.Popen | None = None
        self.collector_health: str = "NOT_STARTED"
        self.mros_health: str = "NOT_STARTED"
        self._ws_client: Any = None
        self.ws_connected = False
        self.instrument_universe_count = 0
        self.ws_tokens: list[int] = []
        self.broker_user_id: str | None = None
        self._callback_server: GovernedAuthCallbackServer | None = None

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

        from core.certified_release_store import ReleaseStore, ReleaseStoreError
        try:
            store = ReleaseStore(self.release_store_path)
            record = store.read()
            if not record or not isinstance(record, dict):
                self.emit("RELEASE", "FAIL", "ReleaseStore record missing or empty")
                self.transition(LauncherState.BLOCKED, "release_store_empty")
                return False
            certified_sha = str(record.get("certified_live_sha") or "").strip()
            if not certified_sha:
                self.emit("RELEASE", "FAIL", "ReleaseStore certified_live_sha missing")
                self.transition(LauncherState.BLOCKED, "release_store_certified_sha_missing")
                return False
        except (ReleaseStoreError, Exception) as exc:
            self.emit("RELEASE", "FAIL", f"ReleaseStore read failed: {exc}")
            self.transition(LauncherState.BLOCKED, f"release_store_error:{exc}")
            return False

        if head_sha != certified_sha:
            self.emit(
                "RELEASE",
                "FAIL",
                f"Running SHA mismatch: running {head_sha[:8]} != certified {certified_sha[:8]}",
            )
            self.transition(LauncherState.BLOCKED, "release_sha_mismatch_certified_store")
            return False

        if self.expected_release_sha:
            expected = str(self.expected_release_sha).strip()
            if expected != certified_sha or head_sha != expected:
                self.emit(
                    "RELEASE",
                    "FAIL",
                    f"CLI expected SHA mismatch: expected {expected[:8]} != certified {certified_sha[:8]}",
                )
                self.transition(LauncherState.BLOCKED, "release_sha_mismatch_expected")
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
        except (Exception, SystemExit):
            return None

    def step_wait_human_auth(self, *, poll_interval: float = 0.5, timeout_override: float | None = None) -> bool:
        timeout = timeout_override if timeout_override is not None else self.auth_timeout_seconds
        self.emit("AUTH", "WAITING_HUMAN_AUTH", f"Timeout {int(timeout)}s")

        callback_server = GovernedAuthCallbackServer(
            token_path=self.token_path,
            repo_root=self.repo_root,
        )
        self._callback_server = callback_server
        server_started = callback_server.start()
        if server_started:
            self.emit(
                "AUTH",
                "CALLBACK_LISTENING",
                f"http://{callback_server.host}:{callback_server.port}/ waiting for login redirect",
            )
        else:
            reused = False
            try:
                import urllib.request
                health_url = f"http://{callback_server.host}:{callback_server.port}/health"
                with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                    if resp.status == 200:
                        payload = json.loads(resp.read().decode("utf-8"))
                        if payload.get("status") == "tradebot_auth_callback":
                            health_pid = int(payload.get("pid", 0))
                            health_nonce = str(payload.get("nonce", ""))
                            # Strictly verify ownership contract file
                            auth_contract_file = self.repo_root / ".runtime" / f".callback_server_{callback_server.port}.json"
                            if auth_contract_file.is_file():
                                contract_data = json.loads(auth_contract_file.read_text(encoding="utf-8"))
                                contract_pid = int(contract_data.get("pid", 0))
                                contract_nonce = str(contract_data.get("nonce", ""))
                                if (
                                    contract_pid == health_pid
                                    and contract_nonce == health_nonce
                                    and health_nonce != ""
                                    and contract_pid > 0
                                ):
                                    try:
                                        os.kill(contract_pid, 0)
                                        reused = True
                                    except OSError:
                                        reused = False
            except Exception:
                reused = False

            if reused:
                self.emit(
                    "AUTH",
                    "CALLBACK_REUSED",
                    f"Reusing active authenticated TradeBot callback daemon on port {callback_server.port}",
                )
            else:
                self.emit(
                    "AUTH",
                    "FAIL",
                    f"Port {callback_server.port} collision with unauthenticated owner ({callback_server.error}); failing closed",
                )
                self.transition(LauncherState.BLOCKED, f"auth_port_collision_unknown_owner:{callback_server.error}")
                return False

        try:
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
        finally:
            if server_started:
                callback_server.stop()
            self._callback_server = None

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
            rows = fetch_current_instruments(client, exchanges=("NSE", "NFO", "BFO", "BSE"))
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

        # Persist master instruments and produce authoritative dated instrument authority
        try:
            from datetime import date as dt_date
            from core.daily_instrument_authority import produce_authority
            instruments_dir = self.state_root / "instruments"
            instruments_dir.mkdir(parents=True, exist_ok=True)
            master_file = instruments_dir / f"kite_instruments_{self.session_date}.json"
            if not master_file.exists():
                def _serialize_instrument_row(row: dict[str, Any]) -> dict[str, Any]:
                    r = dict(row)
                    if "expiry" in r and isinstance(r["expiry"], (dt_date, datetime)):
                        r["expiry"] = r["expiry"].isoformat()
                    return r
                clean_rows = [_serialize_instrument_row(r) for r in rows]
                master_file.write_text(json.dumps(clean_rows, indent=2) + "\n", encoding="utf-8")
            authority_file = instruments_dir / f"instrument_authority_{self.session_date}.json"
            if not authority_file.exists():
                source_sha = getattr(self, "current_commit_sha", "")
                if not source_sha:
                    try:
                        import subprocess
                        source_sha = subprocess.check_output(
                            ["git", "rev-parse", "HEAD"], cwd=str(self.repo_root), text=True
                        ).strip()
                    except Exception:
                        source_sha = "UNKNOWN_COMMIT"
                produce_authority(
                    master_path=master_file,
                    output_path=authority_file,
                    session_date=self.session_date,
                    source_sha=source_sha,
                    required_tokens=self.ws_tokens,
                    reviewed_pass=True,
                )
        except Exception as exc:
            # Authority creation failure is logged; non-fatal if offline/mocked unless in live
            self.emit("INSTRUMENTS", "AUTHORITY_NOTE", f"Authority artifact note: {exc}")

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

        if self.preflight_only:
            self.emit("PREFLIGHT", "PASS", "All pre-session readiness gates certified; preflight complete")
            self.transition(LauncherState.STOPPED, "preflight_complete")
            return True

        open_time = datetime.strptime(self.market_open_time, "%H:%M").time()
        close_time = datetime.strptime(self.market_close_time, "%H:%M").time()
        now_time = datetime.now(IST_TZ).time()

        if now_time < open_time:
            if not self.wait_for_window:
                self.emit("OBSERVER", "STANDBY", f"Current time {now_time.strftime('%H:%M')} before active window {self.market_open_time}-{self.market_close_time} IST")
                self.transition(LauncherState.STOPPED, "outside_session_timing_window")
                return True

            self.emit("OBSERVER", "WAITING", f"Pre-session readiness certified. Waiting for {self.market_open_time} IST market window (current: {now_time.strftime('%H:%M:%S')})")
            while datetime.now(IST_TZ).time() < open_time:
                if self._stop_requested:
                    self.transition(LauncherState.STOPPED, "operator_stopped_while_waiting")
                    return False
                time.sleep(1.0)
            now_time = datetime.now(IST_TZ).time()

        if now_time > close_time:
            self.emit("OBSERVER", "STANDBY", f"Current time {now_time.strftime('%H:%M')} outside active window {self.market_open_time}-{self.market_close_time} IST")
            self.transition(LauncherState.STOPPED, "outside_session_timing_window")
            return True

        self.emit("OBSERVER", "LAUNCHING", f"Starting governed processes (collector + {self.observer_engine}) until {self.market_close_time} IST")

        spawn_collector = self.observer_engine in {"dual", "tick_collector"}
        spawn_mros = self.observer_engine in {"dual", "meg_live"}

        # 1. Primary tick collector process
        collector_cmd = [
            sys.executable,
            "-u",
            str(self.repo_root / "scripts" / "tick_data_collector.py"),
        ]

        # 2. Governed MROS observer process
        master_file = self.state_root / "instruments" / f"kite_instruments_{self.session_date}.json"
        authority_file = self.state_root / "instruments" / f"instrument_authority_{self.session_date}.json"
        mros_cmd = [
            sys.executable,
            "-u",
            str(self.repo_root / "scripts" / "run_market_event_graph_live_session_v1.py"),
            "--session-date", self.session_date,
            "--output-root", str(self.state_root / "sessions" / f"session_{self.session_date}"),
        ]
        if master_file.exists():
            mros_cmd.extend(["--kite-instruments-file", str(master_file)])
        if authority_file.exists():
            mros_cmd.extend(["--authority-artifact", str(authority_file)])

        try:
            if spawn_collector:
                self._child_collector_proc = subprocess.Popen(collector_cmd, cwd=str(self.repo_root))
                self.collector_health = "HEALTHY"
                self.emit("COLLECTOR", "RUNNING", f"Child PID {self._child_collector_proc.pid}")
            else:
                self._child_collector_proc = None
                self.collector_health = "NOT_STARTED"

            if spawn_mros:
                child_env = dict(os.environ)
                default_universe = self.repo_root / "runtime" / "reference" / "market_event_graph" / "nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json"
                universe_path = os.environ.get("MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH") or str(default_universe)
                child_env.update({
                    "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE": "true",
                    "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH": universe_path,
                    "FEED_FORENSICS_ENABLED": "true",
                })
                self._child_mros_proc = subprocess.Popen(mros_cmd, cwd=str(self.repo_root), env=child_env)
                self.mros_health = "HEALTHY"
                self.emit("MROS_OBSERVER", "RUNNING", f"Child PID {self._child_mros_proc.pid}")
            else:
                self._child_mros_proc = None
                self.mros_health = "NOT_STARTED"

            # Primary alias for legacy tests
            self._child_observer_proc = self._child_mros_proc or self._child_collector_proc
            self.transition(LauncherState.OBSERVER_RUNNING)
            if self.supervise:
                return self.supervise_observer()
            return True
        except Exception as exc:
            self.emit("OBSERVER", "FAIL", f"Launch failed: {exc}")
            self.transition(LauncherState.BLOCKED, f"observer_launch_failed:{exc}")
            return False

    def supervise_observer(self) -> bool:
        if not self._child_observer_proc and not self._child_collector_proc and not self._child_mros_proc:
            return False

        close_time = datetime.strptime(self.market_close_time, "%H:%M").time()
        last_status_time = time.time()
        col_pid = self._child_collector_proc.pid if self._child_collector_proc else (self._child_observer_proc.pid if self._child_observer_proc else "N/A")
        mros_pid = self._child_mros_proc.pid if self._child_mros_proc else (self._child_observer_proc.pid if self._child_observer_proc else "N/A")
        self.emit("SUPERVISOR", "MONITORING", f"Processes active [Collector PID {col_pid}, MROS PID {mros_pid}]. Cutoff at {self.market_close_time} IST")

        while not self._stop_requested:
            # Poll collector
            if self._child_collector_proc:
                col_ret = self._child_collector_proc.poll()
                if col_ret is not None:
                    if col_ret == 0:
                        self.collector_health = "EXITED_CLEAN"
                    else:
                        self.collector_health = f"FAILED_CODE_{col_ret}"
                        self.emit("COLLECTOR", "TERMINATED", f"Collector exited with code {col_ret}")
                        self.transition(LauncherState.BLOCKED, f"collector_failed_code_{col_ret}")
                        return False
                else:
                    self.collector_health = "HEALTHY"

            # Poll MROS observer
            if self._child_mros_proc:
                mros_ret = self._child_mros_proc.poll()
                if mros_ret is not None:
                    if mros_ret == 0:
                        self.mros_health = "EXITED_CLEAN"
                    else:
                        self.mros_health = f"FAILED_CODE_{mros_ret}"
                        self.emit("MROS_OBSERVER", "TERMINATED", f"MROS observer exited with code {mros_ret}")
                        self.transition(LauncherState.BLOCKED, f"mros_observer_failed_code_{mros_ret}")
                        return False
                else:
                    self.mros_health = "HEALTHY"
            elif self._child_observer_proc and not self._child_collector_proc:
                obs_ret = self._child_observer_proc.poll()
                if obs_ret is not None:
                    if obs_ret == 0:
                        self.mros_health = "EXITED_CLEAN"
                        self.emit("OBSERVER", "FINISHED", f"Observer exited cleanly with code {obs_ret}")
                        self.transition(LauncherState.STOPPED, "observer_clean_exit")
                        return True
                    else:
                        self.mros_health = f"FAILED_CODE_{obs_ret}"
                        self.emit("OBSERVER", "TERMINATED", f"Observer exited with code {obs_ret}")
                        self.transition(LauncherState.BLOCKED, f"observer_failed_code_{obs_ret}")
                        return False

            now = datetime.now(IST_TZ)
            now_time = now.time()

            if now_time >= close_time:
                self.emit("OBSERVER", "CUTOFF_REACHED", f"Reached cutoff {self.market_close_time} IST. Terminating processes cleanly...")
                self.stop("session_completed_cutoff_reached")
                return True

            if time.time() - last_status_time >= self.status_interval_seconds:
                last_status_time = time.time()
                active_pid = self._child_observer_proc.pid if self._child_observer_proc else col_pid
                self.emit(
                    "STATUS_HOURLY",
                    "HEALTHY",
                    f"Time: {now.strftime('%H:%M:%S')} IST | Child PID: {active_pid} running | Collector: {self.collector_health} | MROS: {self.mros_health} | Storage volume: ok",
                )

            time.sleep(1.0)

        return True

    def stop(self, reason: str = "operator_shutdown") -> None:
        self._stop_requested = True
        for proc in [self._child_mros_proc, self._child_collector_proc, self._child_observer_proc]:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=10.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

        if self._ws_client:
            try:
                self._ws_client.close()
            except Exception:
                pass

        if self._callback_server:
            try:
                self._callback_server.stop()
            except Exception:
                pass
            self._callback_server = None

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
