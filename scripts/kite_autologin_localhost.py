from __future__ import annotations

from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(Path(__file__).with_name("bootstrap.py"))

import os
import re
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from config import config as cfg
from core.auth import validate_kite_startup_credentials
from core.kite_client import kite_client
from core.auth_health import get_kite_auth_health
from core.security_guard import local_token_path, write_local_kite_access_token


HOST = "127.0.0.1"
# Dedicated auth callback port. Do not share with webhook/test services.
PORT = 8765
CALLBACK_PATH = "/"
DEFAULT_TIMEOUT_SEC = 180


def _governed_credential_path() -> Path:
    """Return the operator-managed credential file, never a repository file."""
    return Path(
        os.getenv(
            "KITE_CREDENTIALS_PATH",
            str(Path.home() / ".tradebot" / "credentials" / "kite_app.env"),
        )
    ).expanduser().resolve()


def _load_governed_credentials() -> dict[str, str]:
    path = _governed_credential_path()
    if not path.is_file():
        raise SystemExit("Governed Kite credential file is missing.")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*(?:export\s+)?(KITE_API_KEY|KITE_API_SECRET)\s*=\s*(.*?)\s*$", raw_line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip("\"'")
    if not values.get("KITE_API_KEY") or not values.get("KITE_API_SECRET"):
        raise SystemExit("Governed Kite credential file is incomplete.")
    return values


def _resolve_governed_credential(name: str) -> str:
    governed = _load_governed_credentials()[name]
    ambient = str(os.getenv(name) or "").strip()
    if ambient and ambient != governed:
        raise SystemExit(f"{name} conflicts with governed credential source.")
    if bool(re.search(r"\s", governed)):
        raise SystemExit(f"{name} contains whitespace; fix governed credential file.")
    return governed


def _looks_placeholder_api_key(value: str) -> bool:
    token = str(value or "").strip().lower()
    if not token:
        return True
    if token.startswith("your_") or "placeholder" in token:
        return True
    return token in {
        "your_kiteconnect_api_key",
        "your_kite_api_key",
        "your_api_key",
        "changeme",
    }


def _tail4(value: str) -> str:
    raw = str(value or "")
    if len(raw) <= 4:
        return raw
    return raw[-4:]


@dataclass
class CallbackState:
    request_token: str | None = None
    error: str | None = None


STATE = CallbackState()


class ReusableHTTPServer(HTTPServer):
    allow_reuse_address = True


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            request_token = (qs.get("request_token") or [None])[0]
            status = (qs.get("status") or [None])[0]
            action = (qs.get("action") or [None])[0]

            if parsed.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return

            if request_token:
                STATE.request_token = str(request_token).strip()
                body = (
                    "<html><body>"
                    "<h2>Login received</h2>"
                    "<p>You can close this tab and return to the terminal.</p>"
                    "</body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
                return

            STATE.error = f"missing_request_token status={status} action={action}"
            body = (
                "<html><body>"
                "<h2>Callback missing request_token</h2>"
                f"<p>status={status} action={action}</p>"
                "<p>Retry login from the terminal.</p>"
                "</body></html>"
            )
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
        except Exception as exc:
            STATE.error = f"callback_error:{exc}"
            self.send_response(500)
            self.end_headers()

    def log_message(self, _format, *args):
        return


def _run_server(host: str, port: int):
    try:
        httpd = ReusableHTTPServer((host, port), CallbackHandler)
    except OSError as exc:
        STATE.error = f"bind_failed:{exc}"
        return
    httpd.timeout = 0.5
    while STATE.request_token is None and STATE.error is None:
        httpd.handle_request()


def _resolve_api_key() -> str:
    api_key = _resolve_governed_credential("KITE_API_KEY")
    if _looks_placeholder_api_key(api_key):
        raise SystemExit(
            "Invalid or missing KITE_API_KEY. Set a real Kite app key in env/.env before login."
        )
    if bool(re.search(r"\s", api_key)):
        raise SystemExit("KITE_API_KEY contains whitespace; fix env/.env value.")
    return api_key


def _resolve_api_secret() -> str:
    return _resolve_governed_credential("KITE_API_SECRET")


def main():
    # Ensure clean per-run state for reused interpreter sessions.
    STATE.request_token = None
    STATE.error = None

    try:
        validate_kite_startup_credentials(
            repo_root_path=ROOT,
            require_access_token=False,
            require_api_secret=True,
            caller_module=__name__,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc))

    api_key = _resolve_api_key()
    api_secret = _resolve_api_secret()
    api_key_has_whitespace = bool(re.search(r"\s", api_key))

    print(
        "[KITE_AUTH] "
        f"api_key_len={len(api_key)} "
        f"api_key_last4={_tail4(api_key)} "
        f"api_key_has_whitespace={api_key_has_whitespace}"
    )

    server_thread = threading.Thread(target=_run_server, args=(HOST, PORT), daemon=True)
    server_thread.start()

    login_url = kite_client.login_url(api_key=api_key)

    print("\nOpen this URL in your browser and login/approve:\n")
    print(login_url)
    print(f"\nWaiting for redirect on http://{HOST}:{PORT}{CALLBACK_PATH} ...\n")
    try:
        webbrowser.open(login_url)
    except Exception:
        pass

    deadline = time.time() + DEFAULT_TIMEOUT_SEC
    while (
        time.time() < deadline and STATE.request_token is None and STATE.error is None
    ):
        time.sleep(0.2)

    if STATE.error:
        raise SystemExit(
            f"Callback failed: {STATE.error}\n"
            f"If port {PORT} is in use, run: lsof -i :{PORT} and stop the process."
        )
    if not STATE.request_token:
        raise SystemExit("Timed out waiting for request_token. Retry login flow.")

    data = kite_client.generate_session(
        STATE.request_token, api_secret=api_secret, api_key=api_key
    )
    access_token = str(data.get("access_token", "")).strip()
    if not access_token:
        raise SystemExit("No access_token returned by Kite generate_session.")

    print(
        "[KITE_AUTH] "
        f"access_token_len={len(access_token)} "
        f"access_token_last4={_tail4(access_token)} "
        f"access_token_has_whitespace={bool(re.search(r'\\s', access_token))}"
    )

    kite_client.set_access_token(access_token)
    kite_client.ensure()
    margins = kite_client.kite.margins()
    if margins is None:
        raise SystemExit("Kite session validation failed (margins_missing).")

    token_path = write_local_kite_access_token(access_token)
    auth_payload = get_kite_auth_health(force=True)
    if not auth_payload.get("ok"):
        try:
            token_path.unlink()
        except Exception:
            pass
        raise SystemExit(
            f"Kite session validation failed (profile): {auth_payload.get('error')}"
        )

    user_id = str(auth_payload.get("user_id", "") or "")
    broker = str(auth_payload.get("broker", "") or "")
    margin_keys = (
        ",".join(sorted(list((margins or {}).keys()))[:5])
        if isinstance(margins, dict)
        else "UNKNOWN"
    )

    print(f"Saved access_token to: {token_path}")
    print(f"Verified profile user_last4={_tail4(user_id)} broker={broker}")
    print(f"Verified margins keys={margin_keys}")
    print(f"Runtime token source: {local_token_path()}")
    print("\nNow run:\n  python main.py\n")


if __name__ == "__main__":
    main()
