import pytest
import multiprocessing
import os
import core.kite_depth_ws as ws
from config import config as cfg

def test_restart_depth_ws_does_not_call_os_exit_in_main_process(monkeypatch):
    exits = []
    monkeypatch.setattr(os, "_exit", lambda code: exits.append(code))
    monkeypatch.setattr(cfg, "FEED_USE_SUBPROCESS", True, raising=False)
    
    # Mock current process name to MainProcess
    class MockProcess:
        name = "MainProcess"
    monkeypatch.setattr(multiprocessing, "current_process", lambda: MockProcess())
    
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_resubscribe_token_selection", lambda *args, **kwargs: ([101], {}), raising=False)
    monkeypatch.setattr(ws, "stop_depth_ws", lambda **kwargs: None)
    monkeypatch.setattr(ws, "start_depth_ws", lambda *args, **kwargs: None)
    
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    ret = ws.restart_depth_ws([101])
    print("RETURN VALUE:", ret, "\nEVENTS:", events)
    
    assert len(exits) == 0, "os._exit was called from the MainProcess!"

def test_restart_depth_ws_calls_os_exit_in_child_process(monkeypatch):
    exits = []
    monkeypatch.setattr(os, "_exit", lambda code: exits.append(code))
    monkeypatch.setattr(cfg, "FEED_USE_SUBPROCESS", True, raising=False)
    
    class MockProcess:
        name = "KiteDepthWS_Child"
    monkeypatch.setattr(multiprocessing, "current_process", lambda: MockProcess())
    
    monkeypatch.setattr(ws, "_LAST_FULL_RESTART_EPOCH", 0.0, raising=False)
    monkeypatch.setattr(ws, "_resubscribe_token_selection", lambda *args, **kwargs: ([101], {}), raising=False)
    
    events = []
    monkeypatch.setattr(ws, "_log_ws", lambda event, payload: events.append((event, payload)))
    ret = ws.restart_depth_ws([101])
    print("RETURN VALUE:", ret, "\nEVENTS:", events)
    
    assert len(exits) == 1, "os._exit was not called in the child process!"
    assert exits[0] == 1
