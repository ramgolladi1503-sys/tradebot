#!/usr/bin/env python3
"""Authenticated localhost HTTP facade for the MROS local agent bridge."""

from __future__ import annotations

import argparse
import hmac
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from mros_agent_bridge import BridgeError, MrosAgentBridge, load_config


class BridgeHandler(BaseHTTPRequestHandler):
    bridge: MrosAgentBridge
    token: str

    server_version = "MROSAgentBridge/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        # Avoid dumping authorization headers or request bodies.
        super().log_message(fmt, *args)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        expected = f"Bearer {self.token}"
        return hmac.compare_digest(header, expected)

    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _require_auth(self) -> bool:
        if not self._authorized():
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "UNAUTHORIZED"})
            return False
        return True

    def _read_json(self) -> dict:
        length_raw = self.headers.get("Content-Length", "0")
        try:
            length = int(length_raw)
        except ValueError as exc:
            raise BridgeError("CONTENT_LENGTH_INVALID") from exc
        if length <= 0 or length > 64 * 1024:
            raise BridgeError("REQUEST_BODY_SIZE_INVALID")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise BridgeError("REQUEST_JSON_INVALID") from exc
        if not isinstance(payload, dict):
            raise BridgeError("REQUEST_JSON_OBJECT_REQUIRED")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            if not self._require_auth():
                return
            self._send(HTTPStatus.OK, self.bridge.health())
            return
        if path.startswith("/mros/jobs/"):
            if not self._require_auth():
                return
            job_id = path.removeprefix("/mros/jobs/")
            try:
                record = self.bridge.get(job_id)
            except BridgeError as exc:
                status = HTTPStatus.NOT_FOUND if str(exc) == "JOB_NOT_FOUND" else HTTPStatus.BAD_REQUEST
                self._send(status, {"error": str(exc)})
                return
            self._send(HTTPStatus.OK, record.public_dict())
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/mros/jobs":
            self._send(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
            return
        if not self._require_auth():
            return
        try:
            record = self.bridge.submit(self._read_json())
        except BridgeError as exc:
            self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return
        self._send(HTTPStatus.ACCEPTED, record.public_dict())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local MROS isolated-agent bridge")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Intentional localhost-only default. Non-loopback binding requires an explicit opt-in.
    if args.host not in {"127.0.0.1", "::1", "localhost"} and os.environ.get("MROS_ALLOW_NON_LOOPBACK") != "1":
        raise SystemExit("Refusing non-loopback bind without MROS_ALLOW_NON_LOOPBACK=1")
    token = os.environ.get("MROS_AGENT_BRIDGE_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("MROS_AGENT_BRIDGE_TOKEN must contain at least 32 characters")
    bridge = MrosAgentBridge(load_config(args.config))
    handler = type("ConfiguredBridgeHandler", (BridgeHandler,), {"bridge": bridge, "token": token})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(json.dumps({"status": "LISTENING", "host": args.host, "port": args.port, "runtime_authority": "NONE"}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
