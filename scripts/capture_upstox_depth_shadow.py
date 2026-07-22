#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from research.upstox_depth_shadow_capture_v2.session import (
    ShadowDepthSession,
    audit_shadow_session,
)


LOGGER = logging.getLogger("upstox_depth_shadow_v2")
MODE_LIMITS = {"full": 2000, "full_d30": 50}


def _load_keys(paths: Iterable[Path], inline: Iterable[str]) -> list[str]:
    values = [str(value).strip() for value in inline if str(value).strip()]
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = [line.strip() for line in text.splitlines() if line.strip()]
        if isinstance(payload, dict):
            payload = payload.get("instrument_keys")
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON list, instrument_keys list, or one key per line")
        values.extend(str(value).strip() for value in payload if str(value).strip())
    return sorted(set(values))


def _disconnect(streamer: Any) -> None:
    for method_name in ("disconnect", "close"):
        method = getattr(streamer, method_name, None)
        if callable(method):
            try:
                method()
            except Exception as exc:  # pragma: no cover - SDK/runtime boundary
                LOGGER.warning("Streamer %s failed: %s", method_name, exc)
            return


def _run_fixture(args: argparse.Namespace, keys: list[str]) -> int:
    session = ShadowDepthSession(
        output_root=args.output_root,
        requested_instrument_keys=keys,
        mode=args.mode,
        chunk_rows=args.chunk_rows,
        flush_seconds=args.flush_seconds,
        session_date=args.session_date,
    )
    payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    messages = payload if isinstance(payload, list) else [payload]
    for message in messages:
        session.record_message(message)
    session.finalize()
    result = audit_shadow_session(session.session_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["classification"] else 1


def _run_live(args: argparse.Namespace, keys: list[str]) -> int:
    token = os.getenv(args.access_token_env, "").strip()
    if not token:
        raise RuntimeError(f"{args.access_token_env} is missing or empty")

    try:
        import upstox_client
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("install upstox-python-sdk before live shadow capture") from exc

    configuration = upstox_client.Configuration()
    configuration.access_token = token
    api_client = upstox_client.ApiClient(configuration)
    streamer = upstox_client.MarketDataStreamerV3(api_client, keys, args.mode)
    auto_reconnect = getattr(streamer, "auto_reconnect", None)
    if callable(auto_reconnect):
        auto_reconnect(True, args.reconnect_interval_seconds, args.reconnect_retries)

    session = ShadowDepthSession(
        output_root=args.output_root,
        requested_instrument_keys=keys,
        mode=args.mode,
        chunk_rows=args.chunk_rows,
        flush_seconds=args.flush_seconds,
        session_date=args.session_date,
    )
    stop = threading.Event()

    def request_stop(signum: int, _frame: Any) -> None:
        LOGGER.info("Received signal %s; finalizing shadow capture", signum)
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    def on_message(message: Any) -> None:
        session.record_message(message)

    def on_error(error: Any) -> None:
        LOGGER.error("Upstox market-stream error: %s", error)
        session.note_stream_error(error)

    def on_close(*details: Any) -> None:
        LOGGER.warning("Upstox market stream closed: %s", details)
        session.note_close(*details)

    def on_reconnecting(message: Any = None) -> None:
        LOGGER.warning("Upstox market stream reconnecting: %s", message)
        session.note_reconnecting(message)

    def on_reconnect_stopped(message: Any = None) -> None:
        session.note_stream_error(f"AUTO_RECONNECT_STOPPED:{message}")
        stop.set()

    streamer.on("message", on_message)
    streamer.on("error", on_error)
    streamer.on("close", on_close)
    streamer.on("reconnecting", on_reconnecting)
    streamer.on("autoReconnectStopped", on_reconnect_stopped)

    LOGGER.info(
        "Starting research-only Upstox V3 depth capture: mode=%s instruments=%d output=%s",
        args.mode,
        len(keys),
        session.session_dir,
    )
    started = time.monotonic()
    try:
        streamer.connect()
        while not stop.wait(timeout=1.0):
            if args.duration_seconds > 0 and time.monotonic() - started >= args.duration_seconds:
                LOGGER.info("Configured capture duration completed")
                break
            session.flush()
    finally:
        _disconnect(streamer)
        manifest = session.finalize()
        LOGGER.info(
            "Shadow capture finalized: records=%s parse_failures=%s chunks=%s",
            manifest["counters"].get("records_flushed", 0),
            manifest["counters"].get("parse_failures", 0),
            manifest["chunk_count"],
        )

    result = audit_shadow_session(session.session_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Research-only Upstox V3 full-depth shadow recorder. No orders or execution."
    )
    parser.add_argument("--instrument-key", action="append", default=[])
    parser.add_argument("--instrument-file", action="append", type=Path, default=[])
    parser.add_argument("--mode", choices=sorted(MODE_LIMITS), default="full")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(".runtime/research/upstox_depth_shadow_v2"),
    )
    parser.add_argument("--session-date", help="Override session date as YYYYMMDD")
    parser.add_argument("--chunk-rows", type=int, default=10_000)
    parser.add_argument("--flush-seconds", type=float, default=60.0)
    parser.add_argument("--duration-seconds", type=float, default=23_400.0)
    parser.add_argument("--access-token-env", default="UPSTOX_ACCESS_TOKEN")
    parser.add_argument("--reconnect-interval-seconds", type=int, default=10)
    parser.add_argument("--reconnect-retries", type=int, default=20)
    parser.add_argument(
        "--fixture",
        type=Path,
        help="Parse one JSON message or list of messages without connecting to Upstox",
    )
    parser.add_argument(
        "--audit-only",
        type=Path,
        help="Audit an existing shadow session directory and exit",
    )
    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )
    args = build_parser().parse_args()
    if args.audit_only:
        result = audit_shadow_session(args.audit_only)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    keys = _load_keys(args.instrument_file, args.instrument_key)
    if not keys:
        raise SystemExit("provide --instrument-key or --instrument-file")
    limit = MODE_LIMITS[args.mode]
    if len(keys) > limit:
        raise SystemExit(
            f"{args.mode} supports at most {limit} instrument keys under the frozen recorder contract"
        )
    if args.fixture:
        return _run_fixture(args, keys)
    return _run_live(args, keys)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        LOGGER.error("Shadow depth capture failed: %s", exc)
        raise
