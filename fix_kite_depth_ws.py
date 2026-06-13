import re
with open("core/kite_depth_ws.py", "r") as f:
    code = f.read()

target1 = """    def on_connect(ws, response):
        global _STALE_STRIKES, _WARMUP_PENDING, _RUNTIME_STATE, _LAST_RUNTIME_ERROR
        try:
            _clear_last_disconnected_info()
            _record_feed_restart_verify_connect(now_epoch=float(now_utc_epoch()))
            _log_ws("ws_connected", {"response": str(response), "ws_lifecycle_state": "CONNECTED"})
            _log_ws("FEED_CONNECT", {"tokens": len(tokens), "response": str(response)})
            logger.info(
                "depth_ws_connected token_count=%d first_tokens=%s",
                len(tokens or []),
                list((tokens or [])[:10]),
            )
            # Reset stale tracker and invalidate pre-existing depth timestamps so
            # watchdog waits for fresh post-connect ticks.
            _STALE_STRIKES = 0
            _WARMUP_PENDING = True
            for book in list(depth_store.books.values()):
                if isinstance(book, dict):
                    book["ts_epoch"] = None
                    book["ts"] = None
            _resubscribe_full(ws, reason="connect")
            _RUNTIME_STATE = "RUNNING"
            _LAST_RUNTIME_ERROR = ""
            _persist_runtime_snapshot_row(
                ws_connected=True,
                source="on_connect",
                runtime_state="RUNNING",
                last_error="",
            )
        except Exception as exc:
            _RUNTIME_STATE = "SUBSCRIBE_FAILED"
            _LAST_RUNTIME_ERROR = str(exc)
            _log_ws("FEED_CONNECT_ERROR", {"error": str(exc)})
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source="on_connect:error",
                runtime_state="SUBSCRIBE_FAILED",
                last_error=_LAST_RUNTIME_ERROR,
            )

    def on_reconnect(ws, attempts):
        global _RUNTIME_STATE, _LAST_RUNTIME_ERROR
        try:
            _clear_last_disconnected_info()
            _record_feed_restart_verify_connect(now_epoch=float(now_utc_epoch()))
            _log_ws("ws_reconnect_success", {"attempts": attempts, "ws_lifecycle_state": "CONNECTED"})
            _resubscribe_full(ws, reason=f"reconnect:{attempts}")
            _RUNTIME_STATE = "RUNNING"
            _LAST_RUNTIME_ERROR = ""
            _persist_runtime_snapshot_row(
                ws_connected=True,
                source=f"on_reconnect:{attempts}",
                runtime_state="RUNNING",
                last_error="",
            )
            _log_ws("FEED_RECONNECT", {"attempts": attempts})
        except Exception as exc:
            _RUNTIME_STATE = "SUBSCRIBE_FAILED"
            _LAST_RUNTIME_ERROR = str(exc)
            _log_ws("FEED_RECONNECT_ERROR", {"error": str(exc), "attempts": attempts})
            _persist_runtime_snapshot_row(
                ws_connected=False,
                source=f"on_reconnect:{attempts}:error",
                runtime_state="SUBSCRIBE_FAILED",
                last_error=_LAST_RUNTIME_ERROR,
            )"""

replacement1 = """    def on_connect(ws, response):
        try:
            _clear_last_disconnected_info()
            _log_ws("ws_connect_handshake_started", {"response": str(response), "ws_lifecycle_state": "CONNECTING"})
        except Exception as exc:
            _log_ws("FEED_CONNECT_HANDSHAKE_ERROR", {"error": str(exc)})

    def on_open(ws):
        global _STALE_STRIKES, _WARMUP_PENDING, _RUNTIME_STATE, _LAST_RUNTIME_ERROR
        try:
            _record_feed_restart_verify_connect(now_epoch=float(now_utc_epoch()))
            _log_ws("ws_connected", {"ws_lifecycle_state": "CONNECTED"})
            _log_ws("FEED_CONNECT", {"tokens": len(tokens)})
            logger.info(
                "depth_ws_connected token_count=%d first_tokens=%s",
                len(tokens or []),
                list((tokens or [])[:10]),
            )
            # Reset stale tracker and invalidate pre-existing depth timestamps so
            # watchdog waits for fresh post-connect ticks.
            _STALE_STRIKES = 0
            _WARMUP_PENDING = True
            for book in list(depth_store.books.values()):
                if isinstance(book, dict):
                    book["ts_epoch"] = None
                    book["ts"] = None
            _resubscribe_full(ws, reason="open")
            _RUNTIME_STATE = "RUNNING"
            _LAST_RUNTIME_ERROR = ""
            _persist_runtime_snapshot_row(
                ws_connected=True,
                source="on_open",
                runtime_state="RUNNING",
                last_error="",
            )
        except Exception as exc:
            _RUNTIME_STATE = "SUBSCRIBE_FAILED"
            _LAST_RUNTIME_ERROR = str(exc)
            _log_ws("FEED_SUBSCRIBE_ERROR", {"error": str(exc)})
            _persist_runtime_snapshot_row(
                ws_connected=True,
                source="on_open:error",
                runtime_state="SUBSCRIBE_FAILED",
                last_error=_LAST_RUNTIME_ERROR,
            )

    def on_reconnect(ws, attempts):
        try:
            _log_ws("ws_reconnect_attempt", {"attempts": attempts, "ws_lifecycle_state": "RECONNECTING"})
            _log_ws("FEED_RECONNECT_ATTEMPT", {"attempts": attempts})
        except Exception as exc:
            _log_ws("FEED_RECONNECT_ERROR", {"error": str(exc), "attempts": attempts})"""

target2 = """    kws.on_connect = on_connect
    kws.on_reconnect = on_reconnect
    kws.on_error = on_error
    kws.on_close = on_close
    kws.on_ticks = on_ticks"""

replacement2 = """    kws.on_connect = on_connect
    kws.on_open = on_open
    kws.on_reconnect = on_reconnect
    kws.on_error = on_error
    kws.on_close = on_close
    kws.on_ticks = on_ticks"""

if target1 in code:
    code = code.replace(target1, replacement1)
    if target2 in code:
        code = code.replace(target2, replacement2)
        with open("core/kite_depth_ws.py", "w") as f:
            f.write(code)
        print("Successfully updated core/kite_depth_ws.py")
    else:
        print("Error: Target 2 not found")
else:
    print("Error: Target 1 not found")
