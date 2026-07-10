import re

with open("core/kite_depth_ws.py", "r") as f:
    content = f.read()

new_func = """def _run_db_tick_watchdog_cycle(
    *,
    now_epoch: float,
    market_open: bool,
    stale_restart_sec: float,
    reset_sec: float = 2.0,
    strikes_to_restart: int = 2,
    restart_cb=None,
) -> dict:
    global _STALE_STRIKES, _LAST_MSG_TS_BY_TOKEN, _UNDERLYING_TOKENS, _LAST_TOKENS
    db_tick_epoch = _latest_db_tick_epoch()
    db_tick_age_sec = None
    if db_tick_epoch is not None:
        db_tick_age_sec = max(0.0, float(now_epoch) - float(db_tick_epoch))
    ws_tick_epoch = _LAST_WS_TICK_EPOCH if _LAST_WS_TICK_EPOCH > 0 else None
    ws_tick_age_sec = None
    if ws_tick_epoch is not None:
        ws_tick_age_sec = max(0.0, float(now_epoch) - float(ws_tick_epoch))
    restarted = False

    transport_stale_sec = float(stale_restart_sec)
    anchor_stale_sec = max(15.0, float(stale_restart_sec))

    valid_ages = [now_epoch - ts for ts in _LAST_MSG_TS_BY_TOKEN.values() if ts is not None]
    if ws_tick_age_sec is not None:
        valid_ages.append(ws_tick_age_sec)
    last_any_packet_age = min(valid_ages) if valid_ages else 9999.0

    ws_transport_ok = last_any_packet_age <= transport_stale_sec

    anchor_tokens = _UNDERLYING_TOKENS
    active_trade_tokens = [tok for tok in _LAST_TOKENS if tok not in anchor_tokens]

    stale_anchor_tokens = []
    for token in anchor_tokens:
        if token not in _LAST_MSG_TS_BY_TOKEN or _LAST_MSG_TS_BY_TOKEN[token] is None:
            stale_anchor_tokens.append(token)
        elif (now_epoch - _LAST_MSG_TS_BY_TOKEN[token]) > anchor_stale_sec:
            stale_anchor_tokens.append(token)

    anchor_fresh_ok = len(stale_anchor_tokens) == 0

    subscribed_stale_tokens = [
        token for token in active_trade_tokens
        if token in _LAST_MSG_TS_BY_TOKEN and _LAST_MSG_TS_BY_TOKEN[token] is not None and (now_epoch - _LAST_MSG_TS_BY_TOKEN[token]) > transport_stale_sec
    ]

    # Shared runtime state instead of in-process global
    try:
        from core.events import write_json_atomic
        from core.log_writer import logs_dir
        health_path = logs_dir() / "feed_health.json"
        write_json_atomic(health_path, {"subscribed_stale_tokens": list(subscribed_stale_tokens)})
    except Exception as exc:
        pass

    feed_ok = ws_transport_ok and anchor_fresh_ok

    if not market_open:
        _STALE_STRIKES = 0
    elif feed_ok:
        if _STALE_STRIKES:
            _log_ws(
                "FEED_TICK_RECOVERED",
                {
                    "ws_transport_ok": ws_transport_ok,
                    "anchor_fresh_ok": anchor_fresh_ok,
                    "strikes": _STALE_STRIKES,
                },
            )
        _STALE_STRIKES = 0
        _emit_feed_health(
            "FEED_HEALTH_OK",
            {
                "reason": "ws_ticks_flowing_and_anchors_fresh",
                "last_ws_tick_epoch": ws_tick_epoch,
                "last_ws_tick_age_sec": ws_tick_age_sec,
                "stale_anchor_tokens": stale_anchor_tokens,
                "subscribed_stale_tokens": subscribed_stale_tokens,
                "stale_strikes": 0,
            },
        )
    else:
        stale_source = "transport" if not ws_transport_ok else "anchors"
        stale_age = last_any_packet_age if not ws_transport_ok else anchor_stale_sec + 0.1

        _STALE_STRIKES += 1
        _log_ws(
            "FEED_TICK_STALE",
            {"age_sec": stale_age, "source": stale_source, "strikes": _STALE_STRIKES, "stale_anchors": stale_anchor_tokens},
            throttle_key="FEED_TICK_STALE",
        )
        _emit_feed_health(
            "FEED_STALE",
            {
                "reason": f"{stale_source}_tick_stale",
                "last_ws_tick_epoch": ws_tick_epoch,
                "last_ws_tick_age_sec": ws_tick_age_sec,
                "stale_anchor_tokens": stale_anchor_tokens,
                "subscribed_stale_tokens": subscribed_stale_tokens,
                "stale_strikes": int(_STALE_STRIKES),
            },
        )
        if _STALE_STRIKES >= max(1, int(strikes_to_restart)):
            cb = restart_cb or restart_depth_ws
            try:
                restarted = bool(
                    cb(
                        reason="tick_stalled",
                        ignore_cooldown=True,
                        force_full_restart=True,
                    )
                )
            except TypeError:
                try:
                    restarted = bool(
                        cb(
                            reason="tick_stalled",
                            ignore_cooldown=True,
                        )
                    )
                except TypeError:
                    restarted = bool(cb("tick_stalled"))

    return {
        "last_db_tick_epoch": db_tick_epoch,
        "last_db_tick_age_sec": db_tick_age_sec,
        "last_ws_tick_epoch": ws_tick_epoch,
        "last_ws_tick_age_sec": ws_tick_age_sec,
        "stale_strikes": int(_STALE_STRIKES),
        "restarted": bool(restarted),
    }
"""

pattern = re.compile(r"def _run_db_tick_watchdog_cycle\([^)]+\)\s*->\s*dict:.*?(?=\ndef _)", re.DOTALL)
new_content = pattern.sub(new_func + "\n", content)

with open("core/kite_depth_ws.py", "w") as f:
    f.write(new_content)
