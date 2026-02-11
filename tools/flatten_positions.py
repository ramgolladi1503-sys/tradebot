from tools.legacy import flatten_positions as _legacy

cfg = _legacy.cfg
kite_client = _legacy.kite_client
send_telegram_message = _legacy.send_telegram_message


def _sync_legacy_globals() -> None:
    _legacy.cfg = cfg
    _legacy.kite_client = kite_client
    _legacy.send_telegram_message = send_telegram_message


def _flatten(net, dry_run=False):
    _sync_legacy_globals()
    return _legacy._flatten(net, dry_run=dry_run)


def main():
    _sync_legacy_globals()
    return _legacy.main()


if __name__ == "__main__":
    raise SystemExit(main())
