from __future__ import annotations

import threading
import time

from core.sqlite_write_lock import sqlite_transaction_lock


def test_sqlite_transaction_lock_serializes_threads():
    entered: list[str] = []
    release = threading.Event()
    second_entered = threading.Event()

    def first_writer() -> None:
        with sqlite_transaction_lock():
            entered.append("first")
            release.wait(timeout=2.0)

    def second_writer() -> None:
        with sqlite_transaction_lock():
            entered.append("second")
            second_entered.set()

    first = threading.Thread(target=first_writer)
    second = threading.Thread(target=second_writer)
    first.start()
    for _ in range(100):
        if entered == ["first"]:
            break
        time.sleep(0.001)
    second.start()

    assert not second_entered.wait(timeout=0.05)
    release.set()
    first.join(timeout=2.0)
    second.join(timeout=2.0)

    assert entered == ["first", "second"]
    assert second_entered.is_set()


def test_sqlite_transaction_lock_is_reentrant():
    with sqlite_transaction_lock():
        with sqlite_transaction_lock():
            pass
